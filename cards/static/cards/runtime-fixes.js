(function () {
  function isNativeAuthenticatedPage() {
    return Boolean(
      document.querySelector('meta[name="push-device-url"]') &&
      typeof window.enableNativePush === 'function' &&
      typeof window.nativePlatform === 'function' &&
      window.nativePlatform()
    );
  }

  async function registerGrantedPush() {
    if (!isNativeAuthenticatedPage()) return;
    try {
      await window.enableNativePush({ requestPermission: false });
    } catch (error) {
      console.error('Automatic push registration failed', error);
    }
  }

  // Register an already-authorized device on every authenticated app session.
  window.addEventListener('load', registerGrantedPush, { once: true });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) registerGrantedPush();
  });

  // Ask once, after a real user interaction, so users do not have to discover
  // the notification settings page before the native token is registered.
  async function requestPushOnce() {
    if (!isNativeAuthenticatedPage()) return;
    if (localStorage.getItem('samsPushPermissionPrompted') === '1') return;
    localStorage.setItem('samsPushPermissionPrompted', '1');
    try {
      await window.enableNativePush({ requestPermission: true });
    } catch (error) {
      console.error('Push permission request failed', error);
    }
  }
  document.addEventListener('pointerup', requestPushOnce, { once: true, passive: true });

  // On phones transaction tables become tappable cards. Links and buttons keep
  // their own actions; tapping the rest of the row opens the receipt.
  document.addEventListener('click', event => {
    const row = event.target.closest('[data-row-link]');
    if (!row || event.target.closest('a,button,input,select,textarea,label,form')) return;
    const target = row.dataset.rowLink;
    if (target) window.location.assign(target);
  });

  document.querySelectorAll('[data-row-link]').forEach(row => {
    row.setAttribute('tabindex', '0');
    row.setAttribute('role', 'link');
    row.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        window.location.assign(row.dataset.rowLink);
      }
    });
  });
})();
