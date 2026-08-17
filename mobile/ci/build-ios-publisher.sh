#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_BUNDLE_ID="de.aplussolution.samscard"
EXPECTED_TEAM_ID="884MVA2MD5"

: "${IOS_BUNDLE_ID:?IOS_BUNDLE_ID is required}"
: "${IOS_TEAM_ID:?IOS_TEAM_ID is required}"
: "${APP_VERSION_NAME:?APP_VERSION_NAME is required}"
: "${APP_BUILD_NUMBER:?APP_BUILD_NUMBER is required}"
: "${IOS_PROVISIONING_PROFILE_SPECIFIER:?IOS_PROVISIONING_PROFILE_SPECIFIER is required}"

[ "$IOS_BUNDLE_ID" = "$EXPECTED_BUNDLE_ID" ] || { echo "Refusing wrong bundle: $IOS_BUNDLE_ID" >&2; exit 31; }
[ "$IOS_TEAM_ID" = "$EXPECTED_TEAM_ID" ] || { echo "Refusing wrong Apple Team: $IOS_TEAM_ID" >&2; exit 32; }
[ "$APP_VERSION_NAME" = "1.0.4" ] || { echo "This release entrypoint is pinned to Sams 1.0.4" >&2; exit 33; }
[ "$APP_BUILD_NUMBER" = "2026081701" ] || { echo "This release entrypoint is pinned to Sams build 2026081701" >&2; exit 34; }

echo "Building Sams Club Lounge $APP_VERSION_NAME ($APP_BUILD_NUMBER) for $IOS_BUNDLE_ID"

XCODE_APP="$(find /Applications -maxdepth 1 -type d -name 'Xcode_26*.app' -print 2>/dev/null | sort -V | tail -n 1 || true)"
if [ -n "$XCODE_APP" ]; then
  sudo xcode-select -s "$XCODE_APP/Contents/Developer"
fi
xcodebuild -version
IOS_SDK_VERSION="$(xcrun --sdk iphoneos --show-sdk-version)"
IOS_SDK_MAJOR="${IOS_SDK_VERSION%%.*}"
[ "$IOS_SDK_MAJOR" -ge 26 ] || { echo "iOS SDK 26+ required, got $IOS_SDK_VERSION" >&2; exit 35; }

export IOS_VERSION_NAME="$APP_VERSION_NAME"
export IOS_BUILD_NUMBER="$APP_BUILD_NUMBER"
export IOS_PROVISIONING_PROFILE_NAME="$IOS_PROVISIONING_PROFILE_SPECIFIER"

pushd mobile >/dev/null
npm install --no-audit --no-fund
rm -rf ios
npx cap add ios
npx cap sync ios
npm run assets:ios
popd >/dev/null

sudo gem install xcodeproj --no-document
ruby mobile/ci/prepare-ios-release.rb

# Assert the generated native project is still Sams before signing anything.
/usr/libexec/PlistBuddy -c 'Print :CFBundleDisplayName' mobile/ios/App/App/Info.plist | grep -Fx 'Sams Club Lounge'
grep -Fq 'PRODUCT_BUNDLE_IDENTIFIER = de.aplussolution.samscard' mobile/ios/App/App.xcodeproj/project.pbxproj

git config --global http.version HTTP/1.1
SOURCE_PACKAGES_DIR="${RUNNER_TEMP:-/tmp}/SAMS-SourcePackages"
rm -rf "$SOURCE_PACKAGES_DIR"
mkdir -p "$SOURCE_PACKAGES_DIR"

if [ -d mobile/ios/App/App.xcworkspace ]; then
  XCODE_CONTAINER=(-workspace mobile/ios/App/App.xcworkspace)
else
  XCODE_CONTAINER=(-project mobile/ios/App/App.xcodeproj)
fi

for ATTEMPT in 1 2 3 4 5; do
  if xcodebuild -resolvePackageDependencies \
      "${XCODE_CONTAINER[@]}" \
      -scheme App \
      -clonedSourcePackagesDirPath "$SOURCE_PACKAGES_DIR" \
      -scmProvider system; then
    break
  fi
  [ "$ATTEMPT" -lt 5 ] || exit 74
  rm -rf "$SOURCE_PACKAGES_DIR/artifacts"
  find "$SOURCE_PACKAGES_DIR" -name '*.download' -delete 2>/dev/null || true
  sleep $((ATTEMPT * 20))
done

ARCHIVE_PATH="${RUNNER_TEMP:-/tmp}/SAMSCard.xcarchive"
rm -rf "$ARCHIVE_PATH"
xcodebuild \
  "${XCODE_CONTAINER[@]}" \
  -scheme App \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE_PATH" \
  -clonedSourcePackagesDirPath "$SOURCE_PACKAGES_DIR" \
  -disableAutomaticPackageResolution \
  archive

EXPORT_PATH="${RUNNER_TEMP:-/tmp}/SAMSCardExport"
EXPORT_OPTIONS="${RUNNER_TEMP:-/tmp}/SAMSExportOptions.plist"
rm -rf "$EXPORT_PATH"
cat > "$EXPORT_OPTIONS" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>export</string>
  <key>signingStyle</key><string>manual</string>
  <key>signingCertificate</key><string>Apple Distribution</string>
  <key>teamID</key><string>${IOS_TEAM_ID}</string>
  <key>provisioningProfiles</key>
  <dict><key>${IOS_BUNDLE_ID}</key><string>${IOS_PROVISIONING_PROFILE_SPECIFIER}</string></dict>
  <key>manageAppVersionAndBuildNumber</key><false/>
  <key>stripSwiftSymbols</key><true/>
  <key>uploadSymbols</key><true/>
</dict>
</plist>
PLIST

xcodebuild -exportArchive \
  -archivePath "$ARCHIVE_PATH" \
  -exportPath "$EXPORT_PATH" \
  -exportOptionsPlist "$EXPORT_OPTIONS"

IPA_PATH="$(find "$EXPORT_PATH" -maxdepth 1 -name '*.ipa' -print -quit)"
[ -n "$IPA_PATH" ] && [ -s "$IPA_PATH" ] || { echo "IPA export missing" >&2; exit 36; }
mkdir -p artifacts
cp "$IPA_PATH" artifacts/sams-club-lounge.ipa
shasum -a 256 artifacts/sams-club-lounge.ipa

echo "Sams Club Lounge IPA ready: artifacts/sams-club-lounge.ipa"
