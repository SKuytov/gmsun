import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'bg.gmsun.app',
  appName: 'gmsun',
  webDir: 'dist',
  android: { allowMixedContent: true },
  server: { androidScheme: 'https', cleartext: true },
  plugins: {
    SplashScreen: { launchShowDuration: 0 },
  },
}

export default config
