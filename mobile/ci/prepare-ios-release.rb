#!/usr/bin/env ruby
# frozen_string_literal: true

require 'fileutils'
require 'xcodeproj'

required = %w[
  IOS_BUNDLE_ID
  IOS_TEAM_ID
  IOS_VERSION_NAME
  IOS_BUILD_NUMBER
  IOS_PROVISIONING_PROFILE_NAME
]
required.each do |name|
  value = ENV[name]
  abort("Erforderliche Umgebungsvariable fehlt: #{name}") if value.nil? || value.strip.empty?
end

mobile_root = File.expand_path('..', __dir__)
ios_root = File.join(mobile_root, 'ios', 'App')
project_path = File.join(ios_root, 'App.xcodeproj')
app_dir = File.join(ios_root, 'App')
info_plist_path = File.join(app_dir, 'Info.plist')
entitlements_path = File.join(app_dir, 'App.entitlements')
app_delegate_path = File.join(app_dir, 'AppDelegate.swift')
launch_storyboard_path = File.join(app_dir, 'Base.lproj', 'LaunchScreen.storyboard')
privacy_manifest_source = File.join(mobile_root, 'ci', 'PrivacyInfo.xcprivacy')
privacy_manifest_path = File.join(app_dir, 'PrivacyInfo.xcprivacy')

abort("Xcode-Projekt fehlt: #{project_path}") unless File.directory?(project_path)
abort("Info.plist fehlt: #{info_plist_path}") unless File.file?(info_plist_path)
abort("AppDelegate.swift fehlt: #{app_delegate_path}") unless File.file?(app_delegate_path)
abort("LaunchScreen.storyboard fehlt: #{launch_storyboard_path}") unless File.file?(launch_storyboard_path)
abort("Privacy Manifest fehlt: #{privacy_manifest_source}") unless File.file?(privacy_manifest_source)

# Capacitor's generated launch storyboard uses iOS systemBackgroundColor, which is
# white in Light Mode. The web app itself is dark, so the hand-off produced a
# visible white flash before WKWebView rendered its first frame. Force the launch
# view to the same dark background as the web/native shell.
launch_storyboard = File.read(launch_storyboard_path)
dark_launch_color = '<color key="backgroundColor" red="0.0196078431" green="0.0117647059" blue="0.0431372549" alpha="1" colorSpace="custom" customColorSpace="sRGB"/>'
patched_launch_storyboard = launch_storyboard.gsub(/<color key="backgroundColor"[^>]*\/>/, dark_launch_color)
abort('LaunchScreen backgroundColor konnte nicht gepatcht werden.') if patched_launch_storyboard == launch_storyboard
File.write(launch_storyboard_path, patched_launch_storyboard)

entitlements = {
  'aps-environment' => 'production',
  'com.apple.developer.associated-domains' => [
    'applinks:app.samsclublounge.de',
    'webcredentials:app.samsclublounge.de',
    'applinks:cards.smarbiz.sbs',
    'webcredentials:cards.smarbiz.sbs'
  ],
  'com.apple.developer.applesignin' => ['Default']
}
Xcodeproj::Plist.write_to_path(entitlements, entitlements_path)
FileUtils.cp(privacy_manifest_source, privacy_manifest_path)

info_plist = Xcodeproj::Plist.read_from_path(info_plist_path)
background_modes = Array(info_plist['UIBackgroundModes'])
background_modes << 'remote-notification' unless background_modes.include?('remote-notification')
info_plist['UIBackgroundModes'] = background_modes
info_plist['UIViewControllerBasedStatusBarAppearance'] = false
info_plist['UIStatusBarStyle'] = 'UIStatusBarStyleLightContent'
info_plist['CFBundleDisplayName'] = 'Sams Club Lounge'
info_plist['CFBundleDevelopmentRegion'] = 'de'
info_plist['CFBundleLocalizations'] = ['de']
info_plist['NSCameraUsageDescription'] = 'Die Kamera wird ausschließlich zum Scannen der QR-Mitgliedskarte verwendet.'
info_plist['NSPhotoLibraryUsageDescription'] = 'Die Fotomediathek wird nur geöffnet, wenn du ausdrücklich ein Bild zur Verwendung in der App auswählst.'
info_plist['NSPhotoLibraryAddUsageDescription'] = 'Ein Bild wird nur auf deinen ausdrücklichen Wunsch in deiner Fotomediathek gespeichert.'
info_plist['NSFaceIDUsageDescription'] = 'Face ID wird verwendet, um den geschützten Verwaltungszugriff bequem und sicher zu bestätigen.'
# The app only relies on exempt encryption provided by Apple frameworks,
# such as HTTPS/TLS connections. This prevents repeated export-compliance
# prompts for future App Store Connect uploads.
info_plist['ITSAppUsesNonExemptEncryption'] = false
Xcodeproj::Plist.write_to_path(info_plist, info_plist_path)

app_delegate = File.read(app_delegate_path)
unless app_delegate.include?('capacitorDidRegisterForRemoteNotifications')
  File.open(app_delegate_path, 'a') do |file|
    file.write <<~SWIFT

      // Bridge APNs callbacks to @capacitor/push-notifications.
      extension AppDelegate {
          func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
              NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, object: deviceToken)
          }

          func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
              NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)
          }
      }
    SWIFT
  end
end

project = Xcodeproj::Project.open(project_path)
target = project.targets.find { |candidate| candidate.name == 'App' }
abort('Xcode Target "App" wurde nicht gefunden.') unless target

privacy_reference = project.files.find do |file|
  ['PrivacyInfo.xcprivacy', 'App/PrivacyInfo.xcprivacy'].include?(file.path)
end
privacy_reference ||= project.main_group.new_file('App/PrivacyInfo.xcprivacy')
unless target.resources_build_phase.files_references.include?(privacy_reference)
  target.resources_build_phase.add_file_reference(privacy_reference, true)
end

review_phase = target.shell_script_build_phases.find { |phase| phase.name == 'App Review compliance gate' }
review_phase ||= target.new_shell_script_build_phase('App Review compliance gate')
review_phase.shell_path = '/bin/bash'
review_phase.shell_script = <<~'SH'
  set -Eeuo pipefail
  APP_BUNDLE="${TARGET_BUILD_DIR}/${WRAPPER_NAME}"
  APP_INFO="${APP_BUNDLE}/Info.plist"
  PRIVACY_MANIFEST="${APP_BUNDLE}/PrivacyInfo.xcprivacy"

  test -f "$APP_INFO" || { echo "Finales Info.plist fehlt: $APP_INFO"; exit 1; }
  CAMERA_REASON="$(/usr/libexec/PlistBuddy -c 'Print :NSCameraUsageDescription' "$APP_INFO" 2>/dev/null || true)"
  PHOTO_REASON="$(/usr/libexec/PlistBuddy -c 'Print :NSPhotoLibraryUsageDescription' "$APP_INFO" 2>/dev/null || true)"
  FACE_ID_REASON="$(/usr/libexec/PlistBuddy -c 'Print :NSFaceIDUsageDescription' "$APP_INFO" 2>/dev/null || true)"
  test -n "$CAMERA_REASON" || { echo "NSCameraUsageDescription fehlt im finalen App-Bundle."; exit 1; }
  test -n "$PHOTO_REASON" || { echo "NSPhotoLibraryUsageDescription fehlt im finalen App-Bundle."; exit 1; }
  test -n "$FACE_ID_REASON" || { echo "NSFaceIDUsageDescription fehlt im finalen App-Bundle."; exit 1; }

  test -f "$PRIVACY_MANIFEST" || { echo "PrivacyInfo.xcprivacy fehlt im finalen App-Bundle."; exit 1; }
  /usr/bin/plutil -lint "$PRIVACY_MANIFEST"
  TRACKING="$(/usr/libexec/PlistBuddy -c 'Print :NSPrivacyTracking' "$PRIVACY_MANIFEST" 2>/dev/null || true)"
  test "$TRACKING" = "false" || { echo "NSPrivacyTracking muss false sein."; exit 1; }

  echo "App Review gate bestanden: Kamera-, Foto- und Face-ID-Hinweise sowie Privacy Manifest sind im Bundle."
SH

target.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['PRODUCT_BUNDLE_IDENTIFIER'] = ENV.fetch('IOS_BUNDLE_ID')
  settings['DEVELOPMENT_TEAM'] = ENV.fetch('IOS_TEAM_ID')
  settings['CODE_SIGN_STYLE'] = 'Manual'
  settings['CODE_SIGN_IDENTITY'] = 'Apple Distribution'
  settings['PROVISIONING_PROFILE_SPECIFIER'] = ENV.fetch('IOS_PROVISIONING_PROFILE_NAME')
  settings['CODE_SIGN_ENTITLEMENTS'] = 'App/App.entitlements'
  settings['MARKETING_VERSION'] = ENV.fetch('IOS_VERSION_NAME')
  settings['CURRENT_PROJECT_VERSION'] = ENV.fetch('IOS_BUILD_NUMBER')
  settings['PRODUCT_NAME'] = 'Sams Club Lounge'
  # iPhone-only App Store availability. iPad can still run it in compatibility mode.
  settings['TARGETED_DEVICE_FAMILY'] = '1'
end

project.save
puts "Sams Club Lounge iOS vorbereitet: #{ENV.fetch('IOS_BUNDLE_ID')} · #{ENV.fetch('IOS_VERSION_NAME')} (#{ENV.fetch('IOS_BUILD_NUMBER')})"
