# Native Sign in with Apple

The iOS app uses Apple's native AuthenticationServices flow through the Capacitor Apple Sign-In plugin. The one-time authorization code is exchanged on the Django server, and the returned Apple identity token is verified for signature, issuer, audience, subject, expiry and nonce before a Django session is created.

The login screen uses Apple-generated button artwork rather than a custom Apple logo. The iOS release target includes the `com.apple.developer.applesignin` entitlement and therefore requires an App Store provisioning profile with the Sign in with Apple capability enabled.
