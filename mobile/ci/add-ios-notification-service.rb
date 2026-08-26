#!/usr/bin/env ruby
# frozen_string_literal: true

require 'fileutils'
require 'xcodeproj'

required = %w[
  IOS_TEAM_ID
  IOS_VERSION_NAME
  IOS_BUILD_NUMBER
  IOS_NOTIFICATION_SERVICE_BUNDLE_ID
  IOS_NOTIFICATION_SERVICE_PROVISIONING_PROFILE_NAME
]
required.each do |name|
  value = ENV[name]
  abort("Erforderliche Umgebungsvariable fehlt: #{name}") if value.nil? || value.strip.empty?
end

mobile_root = File.expand_path('..', __dir__)
ios_root = File.join(mobile_root, 'ios', 'App')
project_path = File.join(ios_root, 'App.xcodeproj')
extension_dir = File.join(ios_root, 'NotificationService')
swift_path = File.join(extension_dir, 'NotificationService.swift')
info_plist_path = File.join(extension_dir, 'Info.plist')

abort("Xcode-Projekt fehlt: #{project_path}") unless File.directory?(project_path)
FileUtils.mkdir_p(extension_dir)

File.write(swift_path, <<~'SWIFT')
  import Foundation
  import UserNotifications

  final class NotificationService: UNNotificationServiceExtension {
      private var contentHandler: ((UNNotificationContent) -> Void)?
      private var bestAttemptContent: UNMutableNotificationContent?
      private var downloadTask: URLSessionDownloadTask?
      private let deliveryLock = NSLock()
      private var didDeliver = false

      override func didReceive(
          _ request: UNNotificationRequest,
          withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void
      ) {
          self.contentHandler = contentHandler
          self.bestAttemptContent = request.content.mutableCopy() as? UNMutableNotificationContent

          guard let imageURL = mediaURL(from: request.content.userInfo),
                imageURL.scheme?.lowercased() == "https" else {
              deliverBestAttempt()
              return
          }

          var urlRequest = URLRequest(url: imageURL)
          urlRequest.timeoutInterval = 20
          urlRequest.cachePolicy = .reloadIgnoringLocalCacheData

          let configuration = URLSessionConfiguration.ephemeral
          configuration.timeoutIntervalForRequest = 20
          configuration.timeoutIntervalForResource = 25
          let session = URLSession(configuration: configuration)

          downloadTask = session.downloadTask(with: urlRequest) { [weak self] temporaryURL, response, error in
              guard let self else { return }
              defer { session.finishTasksAndInvalidate() }

              guard error == nil,
                    let temporaryURL,
                    let httpResponse = response as? HTTPURLResponse,
                    (200...299).contains(httpResponse.statusCode),
                    self.isSupportedImageResponse(httpResponse, url: imageURL) else {
                  self.deliverBestAttempt()
                  return
              }

              do {
                  let attributes = try FileManager.default.attributesOfItem(atPath: temporaryURL.path)
                  let fileSize = (attributes[.size] as? NSNumber)?.int64Value ?? 0
                  guard fileSize > 0, fileSize <= 10 * 1024 * 1024 else {
                      self.deliverBestAttempt()
                      return
                  }

                  let fileExtension = self.fileExtension(for: httpResponse, url: imageURL)
                  let attachmentURL = FileManager.default.temporaryDirectory
                      .appendingPathComponent("sams-notification-\(UUID().uuidString)")
                      .appendingPathExtension(fileExtension)

                  try? FileManager.default.removeItem(at: attachmentURL)
                  try FileManager.default.copyItem(at: temporaryURL, to: attachmentURL)

                  let attachment = try UNNotificationAttachment(
                      identifier: "sams-rich-image",
                      url: attachmentURL,
                      options: nil
                  )
                  self.bestAttemptContent?.attachments = [attachment]
              } catch {
                  // Rich media is optional. The original text notification remains the safe fallback.
              }

              self.deliverBestAttempt()
          }
          downloadTask?.resume()
      }

      override func serviceExtensionTimeWillExpire() {
          downloadTask?.cancel()
          deliverBestAttempt()
      }

      private func mediaURL(from userInfo: [AnyHashable: Any]) -> URL? {
          let directKeys = ["media-url", "image_url", "image-url"]
          for key in directKeys {
              if let value = userInfo[key] as? String,
                 let url = URL(string: value.trimmingCharacters(in: .whitespacesAndNewlines)) {
                  return url
              }
          }

          if let data = userInfo["data"] as? [String: Any] {
              for key in directKeys {
                  if let value = data[key] as? String,
                     let url = URL(string: value.trimmingCharacters(in: .whitespacesAndNewlines)) {
                      return url
                  }
              }
          }
          return nil
      }

      private func isSupportedImageResponse(_ response: HTTPURLResponse, url: URL) -> Bool {
          if let mimeType = response.mimeType?.lowercased(), mimeType.hasPrefix("image/") {
              return true
          }
          return ["jpg", "jpeg", "png", "gif", "webp", "heic", "heif"]
              .contains(url.pathExtension.lowercased())
      }

      private func fileExtension(for response: HTTPURLResponse, url: URL) -> String {
          switch response.mimeType?.lowercased() {
          case "image/jpeg": return "jpg"
          case "image/png": return "png"
          case "image/gif": return "gif"
          case "image/webp": return "webp"
          case "image/heic": return "heic"
          case "image/heif": return "heif"
          default:
              let candidate = url.pathExtension.lowercased()
              return candidate.isEmpty ? "jpg" : candidate
          }
      }

      private func deliverBestAttempt() {
          deliveryLock.lock()
          guard !didDeliver,
                let contentHandler,
                let bestAttemptContent else {
              deliveryLock.unlock()
              return
          }
          didDeliver = true
          self.contentHandler = nil
          deliveryLock.unlock()

          contentHandler(bestAttemptContent)
      }
  }
SWIFT

Xcodeproj::Plist.write_to_path(
  {
    'CFBundleDevelopmentRegion' => 'de',
    'CFBundleDisplayName' => 'SAMS Notification Service',
    'CFBundleExecutable' => '$(EXECUTABLE_NAME)',
    'CFBundleIdentifier' => '$(PRODUCT_BUNDLE_IDENTIFIER)',
    'CFBundleInfoDictionaryVersion' => '6.0',
    'CFBundleName' => '$(PRODUCT_NAME)',
    'CFBundlePackageType' => 'XPC!',
    'CFBundleShortVersionString' => '$(MARKETING_VERSION)',
    'CFBundleVersion' => '$(CURRENT_PROJECT_VERSION)',
    'NSExtension' => {
      'NSExtensionPointIdentifier' => 'com.apple.usernotifications.service',
      'NSExtensionPrincipalClass' => '$(PRODUCT_MODULE_NAME).NotificationService'
    }
  },
  info_plist_path
)

project = Xcodeproj::Project.open(project_path)
app_target = project.targets.find { |candidate| candidate.name == 'App' }
abort('Xcode Target "App" wurde nicht gefunden.') unless app_target

extension_target = project.targets.find { |candidate| candidate.name == 'NotificationService' }
deployment_target = app_target.build_configurations
  .map { |configuration| configuration.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] }
  .compact
  .find { |value| !value.to_s.strip.empty? } || '15.0'

extension_target ||= project.new_target(
  :app_extension,
  'NotificationService',
  :ios,
  deployment_target,
  nil,
  :swift,
  'NotificationService'
)

extension_group = project.main_group.groups.find { |group| group.display_name == 'NotificationService' }
extension_group ||= project.main_group.new_group('NotificationService', 'NotificationService')

swift_reference = extension_group.files.find { |file| file.path == 'NotificationService.swift' }
swift_reference ||= extension_group.new_file('NotificationService.swift')
extension_target.add_file_references([swift_reference])

app_target.add_dependency(extension_target) unless app_target.dependency_for_target(extension_target)
embed_phase = app_target.copy_files_build_phases.find { |phase| phase.name == 'Embed App Extensions' }
embed_phase ||= app_target.new_copy_files_build_phase('Embed App Extensions')
embed_phase.symbol_dst_subfolder_spec = :plugins
embed_phase.add_file_reference(extension_target.product_reference, true)

extension_target.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['PRODUCT_BUNDLE_IDENTIFIER'] = ENV.fetch('IOS_NOTIFICATION_SERVICE_BUNDLE_ID')
  settings['PRODUCT_NAME'] = 'NotificationService'
  settings['PRODUCT_MODULE_NAME'] = 'NotificationService'
  settings['DEVELOPMENT_TEAM'] = ENV.fetch('IOS_TEAM_ID')
  settings['CODE_SIGN_STYLE'] = 'Manual'
  settings['CODE_SIGN_IDENTITY'] = 'Apple Distribution'
  settings['PROVISIONING_PROFILE_SPECIFIER'] = ENV.fetch('IOS_NOTIFICATION_SERVICE_PROVISIONING_PROFILE_NAME')
  settings['INFOPLIST_FILE'] = 'NotificationService/Info.plist'
  settings['GENERATE_INFOPLIST_FILE'] = 'NO'
  settings['MARKETING_VERSION'] = ENV.fetch('IOS_VERSION_NAME')
  settings['CURRENT_PROJECT_VERSION'] = ENV.fetch('IOS_BUILD_NUMBER')
  settings['SWIFT_VERSION'] = '5.0'
  settings['APPLICATION_EXTENSION_API_ONLY'] = 'YES'
  settings['SKIP_INSTALL'] = 'YES'
  settings['TARGETED_DEVICE_FAMILY'] = '1'
  settings['IPHONEOS_DEPLOYMENT_TARGET'] = deployment_target
  settings['LD_RUNPATH_SEARCH_PATHS'] = ['$(inherited)', '@executable_path/Frameworks', '@executable_path/../../Frameworks']
end

project.save
puts "SAMS Notification Service vorbereitet: #{ENV.fetch('IOS_NOTIFICATION_SERVICE_BUNDLE_ID')}"
