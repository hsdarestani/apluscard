import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'de.aplussolution.samscard',
  appName: 'SAMS Card',
  webDir: 'www',
  server: {
    url: 'https://cards.smarbiz.sbs',
    cleartext: false,
    allowNavigation: ['cards.smarbiz.sbs'],
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
