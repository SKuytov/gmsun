# gmsun Android app

The Android app is the same React code packaged with **Capacitor 8** (`frontend/android`). It talks to your
gmsun server over HTTP(S); nothing is stored on the phone except the login token and server address.

## Getting an APK

### From GitHub Actions (no Android Studio needed)

1. Open the repo → **Actions** → **Android APK** → latest run → **Artifacts** → `gmsun-debug-apk`.
2. Copy `app-debug.apk` to the phone, allow installation from unknown sources, install.
3. First launch: enter the server address (e.g. `http://192.168.1.50` or `https://gmsun.example.com`), then e‑mail and password.

The debug APK is signed with a debug key — fine for your own phones. Updating: install the newer APK over the old one.

### Signed release (Play Store or clean updates)

Create a keystore once:

```bash
keytool -genkeypair -v -keystore gmsun-release.keystore -alias gmsun -keyalg RSA -keysize 2048 -validity 10000
base64 -w0 gmsun-release.keystore    # -> ANDROID_KEYSTORE_BASE64
```

Add repository secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`,
then push a tag `v1.0.0`. The workflow attaches `app-release.apk` (and the debug APK) to the GitHub Release.

### Building locally

Requirements: Node 22+, JDK 21, Android SDK (Android Studio).

```bash
cd frontend
npm ci && npm run build
npx cap sync android
npx cap open android          # Android Studio -> Run
# or headless:
cd android && ./gradlew assembleDebug   # app/build/outputs/apk/debug/app-debug.apk
```

## Server address

- Login screen → **Server address** field (shown automatically in the native app).
- Later: Settings → **Server** tab → change + "Test connection".
- Build‑time default: `VITE_API_URL=https://gmsun.example.com npm run build` before `cap sync`.

## Permissions

`INTERNET`, `CAMERA` (take a roof photo directly), `READ_MEDIA_IMAGES` (pick from gallery). Cleartext HTTP is allowed so
the app works with a plain `http://192.168.x.x` server on the office LAN.

## App identity

- Application id: `bg.gmsun.app` (`frontend/android/app/build.gradle`, `capacitor.config.ts`)
- Version: `versionCode` / `versionName` in `frontend/android/app/build.gradle`
- Icons/splash: `frontend/android/app/src/main/res/mipmap-*`, `drawable-*/splash.png`
