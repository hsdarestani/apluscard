import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'de.aplussolution.samscard',
  appName: 'Sams Club Lounge',
  webDir: 'www',
  server: {
    url: 'https://app.samsclublounge.de',
    cleartext: false,
    allowNavigation: ['app.samsclublounge.de', 'cards.smarbiz.sbs'],
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert', 'banner', 'list'],
    },
  },
  ios: {
    contentInset: 'automatic',
    preferredContentMode: 'mobile',
  },
  android: {
    allowMixedContent: false,
    adjustMarginsForEdgeToEdge: 'force',
  },
};

export default config;
