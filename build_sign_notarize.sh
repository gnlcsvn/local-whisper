#!/bin/bash
set -e

# Configuration
APP_NAME="LocalWhisper"
BUNDLE_ID="com.localwhisper.app"
DEVELOPER_ID="Developer ID Application: Gian-Luca Savino (334Y2N472Y)"
ENTITLEMENTS="entitlements.plist"
KEYCHAIN_PROFILE="LocalWhisper-notarize"

DIST_DIR="dist"
APP_PATH="$DIST_DIR/$APP_NAME.app"
DMG_PATH="$DIST_DIR/$APP_NAME.dmg"
DMG_TEMP="$DIST_DIR/${APP_NAME}_temp.dmg"

# Activate virtualenv if present
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

echo "========================================="
echo "  $APP_NAME Build, Sign, Notarize & DMG"
echo "========================================="

# Step 1: Build with PyInstaller
echo ""
echo "[1/5] Building with PyInstaller..."
pyinstaller "$APP_NAME.spec" --noconfirm
echo "  Build complete."

# Step 2: Sign all binaries inside the app bundle (inside-out)
echo ""
echo "[2/5] Signing all binaries inside the app bundle..."

# Sign all .so files
find "$APP_PATH" -name "*.so" -exec codesign --force --options runtime --sign "$DEVELOPER_ID" --entitlements "$ENTITLEMENTS" --timestamp {} \;
echo "  Signed .so files."

# Sign all .dylib files
find "$APP_PATH" -name "*.dylib" -exec codesign --force --options runtime --sign "$DEVELOPER_ID" --entitlements "$ENTITLEMENTS" --timestamp {} \;
echo "  Signed .dylib files."

# Sign all framework binaries
find "$APP_PATH" -path "*/Frameworks/*" -type f -perm +111 ! -name "*.dylib" -exec codesign --force --options runtime --sign "$DEVELOPER_ID" --entitlements "$ENTITLEMENTS" --timestamp {} \;
echo "  Signed framework binaries."

# Sign the main executable
codesign --force --options runtime --sign "$DEVELOPER_ID" --entitlements "$ENTITLEMENTS" --timestamp "$APP_PATH/Contents/MacOS/$APP_NAME"
echo "  Signed main executable."

# Step 3: Sign the app bundle itself
echo ""
echo "[3/5] Signing the app bundle..."
codesign --force --options runtime --sign "$DEVELOPER_ID" --entitlements "$ENTITLEMENTS" --timestamp "$APP_PATH"
echo "  App bundle signed."

# Verify the signature
echo ""
echo "  Verifying signature..."
codesign --verify --deep --strict "$APP_PATH"
echo "  Signature valid."

# Step 4: Create DMG with Applications symlink
echo ""
echo "[4/7] Creating DMG..."

# Clean up any previous DMG artifacts
rm -f "$DMG_PATH" "$DMG_TEMP"
DMG_STAGING="$DIST_DIR/dmg_staging"
rm -rf "$DMG_STAGING"

# Create staging directory with app and Applications symlink
mkdir -p "$DMG_STAGING"
cp -R "$APP_PATH" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

# Create a read-write DMG from the staging directory
hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_STAGING" -ov -format UDRW "$DMG_TEMP"

# Mount the DMG to configure appearance
MOUNT_DIR=$(hdiutil attach -readwrite -noverify "$DMG_TEMP" | grep "/Volumes/" | awk '{print $3}')
echo "  Mounted at: $MOUNT_DIR"

# Set DMG window appearance via AppleScript
osascript <<APPLESCRIPT
tell application "Finder"
    tell disk "$APP_NAME"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        delay 0.5
        set the bounds of container window to {400, 200, 900, 500}
        set viewOptions to the icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to 80
        set position of item "$APP_NAME.app" of container window to {125, 150}
        set position of item "Applications" of container window to {375, 150}
        close
    end tell
end tell
APPLESCRIPT

# Unmount
hdiutil detach "$MOUNT_DIR"

# Convert to compressed read-only DMG
hdiutil convert "$DMG_TEMP" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"
rm -f "$DMG_TEMP"
rm -rf "$DMG_STAGING"
echo "  Created $DMG_PATH"

# Step 5: Sign the DMG
echo ""
echo "[5/7] Signing the DMG..."
codesign --force --sign "$DEVELOPER_ID" --timestamp "$DMG_PATH"
echo "  DMG signed."

# Step 6: Submit DMG for notarization
echo ""
echo "[6/7] Submitting DMG for notarization (this may take a few minutes)..."
xcrun notarytool submit "$DMG_PATH" --keychain-profile "$KEYCHAIN_PROFILE" --wait

# Step 7: Staple the notarization ticket
echo ""
echo "[7/7] Stapling notarization ticket..."
xcrun stapler staple "$DMG_PATH"

echo ""
echo "========================================="
echo "  Done! $DMG_PATH is signed and notarized."
echo "========================================="
echo ""
echo "Ready to distribute: $DMG_PATH"
