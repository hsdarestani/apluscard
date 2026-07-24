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
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
  ios: {
    contentInset: 'automatic',
    preferredContentMode: 'mobile',
  },
  android: {
    allowMixedContent: false,
  },
};

export default config;
