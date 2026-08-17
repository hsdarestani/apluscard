#!/usr/bin/env ruby
# frozen_string_literal: true

mobile_root = File.expand_path('..', __dir__)
app_delegate_path = File.join(mobile_root, 'ios', 'App', 'App', 'AppDelegate.swift')
abort("AppDelegate.swift fehlt: #{app_delegate_path}") unless File.file?(app_delegate_path)

source = File.read(app_delegate_path)
marker = 'SamsVerificationUniversalLinkRouter'
if source.include?(marker)
  puts 'SAMS verification Universal-Link router ist bereits installiert.'
  exit 0
end

old_handler = <<~'SWIFT'.rstrip
    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
        // Called when the app was launched with an activity, including Universal Links.
        // Feel free to add additional processing here, but if you want the App API to support
        // tracking app url opens, make sure to keep this call
        return ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
    }
SWIFT

new_handler = <<~'SWIFT'.rstrip
    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
        // Keep Capacitor's normal Universal-Link notification behavior, then route
        // SAMS verification links into the remote WKWebView so Django receives the GET.
        let proxyResult = ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
        if let url = SamsVerificationUniversalLinkRouter.verificationURL(from: userActivity) {
            SamsVerificationUniversalLinkRouter.route(url, in: window)
        }
        return proxyResult
    }
SWIFT

unless source.include?(old_handler)
  abort('Capacitor AppDelegate Universal-Link-Handler wurde nicht in der erwarteten 8.4.2-Form gefunden.')
end

source = source.sub(old_handler, new_handler)
source = source.rstrip + <<~'SWIFT'


  // Routes only canonical SAMS email-verification Universal Links into the
  // Capacitor web view. The bounded retry covers cold launch while the storyboard
  // and CAPBridgeViewController are still being initialized.
  private enum SamsVerificationUniversalLinkRouter {
      static func verificationURL(from userActivity: NSUserActivity) -> URL? {
          guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
                let url = userActivity.webpageURL,
                url.scheme?.lowercased() == "https",
                url.host?.lowercased() == "app.samsclublounge.de",
                url.path.hasPrefix("/accounts/verify/") else {
              return nil
          }
          return url
      }

      static func route(_ url: URL, in window: UIWindow?, attempt: Int = 0) {
          guard attempt < 40 else { return }

          DispatchQueue.main.async {
              guard let bridgeViewController = window?.rootViewController as? CAPBridgeViewController,
                    let webView = bridgeViewController.webView else {
                  DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                      route(url, in: window, attempt: attempt + 1)
                  }
                  return
              }

              if webView.url != url {
                  webView.load(URLRequest(url: url))
              }
          }
      }
  }
SWIFT

File.write(app_delegate_path, source)
puts 'Capacitor 8.4.2 AppDelegate: SAMS verification Universal-Link routing installiert.'
