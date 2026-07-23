const coarsePointer = window.matchMedia('(pointer: coarse)').matches;
const narrowScreen = window.matchMedia('(max-width: 900px)').matches;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const limitedDevice = typeof navigator.deviceMemory === 'number' && navigator.deviceMemory <= 4;
const lowPowerMode = coarsePointer || narrowScreen || reducedMotion || limitedDevice;
if (lowPowerMode) document.documentElement.classList.add('low-power');

document.addEventListener('visibilitychange', () => {
  document.documentElement.classList.toggle('app-paused', document.hidden);
});
window.addEventListener('pagehide', () => document.documentElement.classList.add('app-paused'));
window.addEventListener('pageshow', () => document.documentElement.classList.remove('app-paused'));

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}), { once: true });
}

document.addEventListener('gesturestart', event => event.preventDefault(), { passive: false });
document.addEventListener('gesturechange', event => event.preventDefault(), { passive: false });
document.addEventListener('gestureend', event => event.preventDefault(), { passive: false });
document.addEventListener('touchmove', event => {
  if (event.touches.length > 1) event.preventDefault();
}, { passive: false });

let lastTouchEnd = 0;
document.addEventListener('touchend', event => {
  const now = Date.now();
  if (now - lastTouchEnd <= 300) event.preventDefault();
  lastTouchEnd = now;
}, { passive: false });

let installPrompt = null;
const installButton = document.getElementById('install-app');

window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  installPrompt = event;
  installButton?.classList.add('visible');
});

installButton?.addEventListener('click', async () => {
  if (!installPrompt) return;
  installPrompt.prompt();
  await installPrompt.userChoice;
  installPrompt = null;
  installButton.classList.remove('visible');
});

window.addEventListener('appinstalled', () => {
  installPrompt = null;
  installButton?.classList.remove('visible');
});

const notificationButton = document.getElementById('notification-button');
const notificationCount = document.getElementById('notification-count');
let previousNotificationCount = Number(notificationCount?.textContent || 0);
let notificationTimer = null;

async function refreshNotificationCount() {
  if (!notificationButton || document.hidden) return;
  try {
    const response = await fetch(notificationButton.dataset.countUrl, {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
      cache: 'no-store'
    });
    if (!response.ok) return;
    const payload = await response.json();
    const count = Number(payload.count || 0);
    if (notificationCount) {
      notificationCount.textContent = String(count);
      notificationCount.hidden = count === 0;
    }
    notificationButton.classList.toggle('has-new-notification', count > previousNotificationCount);
    previousNotificationCount = count;
  } catch (_) {}
}

if (notificationButton) {
  const interval = lowPowerMode ? 90000 : 45000;
  notificationTimer = window.setInterval(refreshNotificationCount, interval);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refreshNotificationCount();
  });
  window.addEventListener('pagehide', () => {
    if (notificationTimer) window.clearInterval(notificationTimer);
  }, { once: true });
}

function nativePushPlugin() {
  return window.Capacitor?.Plugins?.PushNotifications || null;
}

function nativePlatform() {
  const platform = window.Capacitor?.getPlatform?.() || window.Capacitor?.platform || '';
  if (String(platform).toLowerCase() === 'ios') return 'IOS';
  if (String(platform).toLowerCase() === 'android') return 'ANDROID';
  return null;
}

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

function safePushTarget(value) {
  if (!value) return '/mitteilungen/';
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin) return '/mitteilungen/';
    return `${url.pathname}${url.search}${url.hash}`;
  } catch (_) {
    return '/mitteilungen/';
  }
}

async function saveNativePushToken(token) {
  const endpoint = document.querySelector('meta[name="push-device-url"]')?.content;
  const platform = nativePlatform();
  if (!endpoint || !platform || !token) return false;
  const response = await fetch(endpoint, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken()
    },
    body: JSON.stringify({ platform, token })
  });
  if (!response.ok) throw new Error(`Push device registration failed: ${response.status}`);
  localStorage.setItem('samsPushToken', token);
  localStorage.setItem('samsPushPlatform', platform);
  return true;
}

let nativePushListenersReady = false;
async function prepareNativePushListeners(plugin) {
  if (nativePushListenersReady) return;
  nativePushListenersReady = true;

  await plugin.addListener('registration', async token => {
    try {
      await saveNativePushToken(token.value);
      document.dispatchEvent(new CustomEvent('sams:push-status', { detail: { state: 'enabled' } }));
    } catch (error) {
      console.error(error);
      document.dispatchEvent(new CustomEvent('sams:push-status', { detail: { state: 'error' } }));
    }
  });
  await plugin.addListener('registrationError', error => {
    console.error('Native push registration error', error);
    document.dispatchEvent(new CustomEvent('sams:push-status', { detail: { state: 'error' } }));
  });
  await plugin.addListener('pushNotificationReceived', () => {
    refreshNotificationCount();
  });
  await plugin.addListener('pushNotificationActionPerformed', event => {
    const target = event?.notification?.data?.url;
    window.location.assign(safePushTarget(target));
  });
}

async function enableNativePush({ requestPermission = false } = {}) {
  const plugin = nativePushPlugin();
  const platform = nativePlatform();
  if (!plugin || !platform) return 'unavailable';

  await prepareNativePushListeners(plugin);

  if (platform === 'ANDROID' && typeof plugin.createChannel === 'function') {
    await plugin.createChannel({
      id: 'sams_updates',
      name: 'SAMS Mitteilungen',
      description: 'Zahlungen, Guthaben, Angebote und wichtige Kontohinweise',
      importance: 5,
      visibility: 1,
      sound: 'default'
    }).catch(() => {});
  }

  let permissions = await plugin.checkPermissions();
  if (permissions.receive === 'prompt' && requestPermission) {
    permissions = await plugin.requestPermissions();
  }
  if (permissions.receive !== 'granted') return permissions.receive || 'denied';

  await plugin.register();
  return 'registering';
}

const pushEnableButton = document.getElementById('enable-native-push');
const pushStatus = document.getElementById('native-push-status');
if (pushEnableButton && nativePushPlugin() && nativePlatform()) {
  pushEnableButton.hidden = false;
  enableNativePush().catch(() => {});
  pushEnableButton.addEventListener('click', async () => {
    pushEnableButton.disabled = true;
    if (pushStatus) pushStatus.textContent = 'Berechtigung wird geprüft …';
    try {
      const state = await enableNativePush({ requestPermission: true });
      if (state === 'denied') {
        if (pushStatus) pushStatus.textContent = 'Push wurde in den Geräteeinstellungen deaktiviert.';
      } else if (state === 'prompt') {
        if (pushStatus) pushStatus.textContent = 'Push-Berechtigung wurde noch nicht erteilt.';
      } else if (pushStatus) {
        pushStatus.textContent = 'Gerät wird registriert …';
      }
    } catch (error) {
      console.error(error);
      if (pushStatus) pushStatus.textContent = 'Push konnte nicht aktiviert werden.';
    } finally {
      pushEnableButton.disabled = false;
    }
  });
}

document.addEventListener('sams:push-status', event => {
  if (!pushStatus) return;
  if (event.detail?.state === 'enabled') {
    pushStatus.textContent = 'Push-Mitteilungen sind auf diesem Gerät aktiv.';
    pushEnableButton?.classList.add('is-enabled');
    if (pushEnableButton) pushEnableButton.textContent = 'Push aktiviert';
  } else if (event.detail?.state === 'error') {
    pushStatus.textContent = 'Das Gerät konnte nicht registriert werden.';
  }
});

document.addEventListener('click', event => {
  const appleButton = event.target.closest('a.apple-login-button');
  if (appleButton) {
    if (appleButton.dataset.busy === 'true') {
      event.preventDefault();
      return;
    }
    appleButton.dataset.busy = 'true';
    appleButton.setAttribute('aria-disabled', 'true');
    appleButton.classList.add('is-loading');
  }

  const openButton = event.target.closest('[data-dialog-open]');
  if (openButton) document.getElementById(openButton.dataset.dialogOpen)?.showModal();

  if (event.target.closest('[data-dialog-close]')) {
    event.target.closest('dialog')?.close();
  }

  const tabButton = event.target.closest('[data-tab]');
  if (tabButton) {
    const wrapper = tabButton.closest('.action-panel');
    wrapper?.querySelectorAll('.tab-button').forEach(button => {
      button.classList.toggle('active', button === tabButton);
    });
    wrapper?.querySelectorAll('.tab-content').forEach(panel => {
      panel.classList.toggle('active', panel.id === tabButton.dataset.tab);
    });
  }
});

document.querySelectorAll('dialog').forEach(dialog => {
  dialog.addEventListener('click', event => {
    if (event.target === dialog) dialog.close();
  });
});

if (!lowPowerMode && 'IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08 });

  document.querySelectorAll('.feature-card, .stat-card, .quick-action').forEach((element, index) => {
    element.style.opacity = '0';
    element.style.transform = 'translateY(14px)';
    element.style.transition = `opacity .35s ease ${Math.min(index, 5) * 35}ms, transform .35s ease ${Math.min(index, 5) * 35}ms`;
    observer.observe(element);
  });
}
