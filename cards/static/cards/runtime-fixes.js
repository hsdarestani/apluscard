(function () {
  const RELEASE_VERSION_URL = '/release/version/';
  let loadedReleaseVersion = null;
  let releaseCheckPromise = null;
  let releaseCheckTimer = null;
  let broadcastPreviewUrl = null;

  async function checkReleaseVersion() {
    if (releaseCheckPromise) return releaseCheckPromise;

    releaseCheckPromise = (async () => {
      try {
        const separator = RELEASE_VERSION_URL.includes('?') ? '&' : '?';
        const response = await fetch(`${RELEASE_VERSION_URL}${separator}_=${Date.now()}`, {
          method: 'GET',
          credentials: 'same-origin',
          cache: 'no-store',
          headers: { Accept: 'application/json' }
        });
        if (!response.ok) return;

        const payload = await response.json();
        const latestVersion = String(payload.version || '').trim();
        if (!latestVersion) return;

        if (!loadedReleaseVersion) {
          loadedReleaseVersion = latestVersion;
          return;
        }

        if (latestVersion !== loadedReleaseVersion) {
          const target = new URL(window.location.href);
          target.searchParams.set('_release', latestVersion);
          window.location.replace(target.toString());
        }
      } catch (_) {
        // A temporary network problem must never interrupt the active app flow.
      }
    })().finally(() => {
      releaseCheckPromise = null;
    });

    return releaseCheckPromise;
  }

  function startReleaseChecks() {
    checkReleaseVersion();
    if (releaseCheckTimer) window.clearInterval(releaseCheckTimer);
    releaseCheckTimer = window.setInterval(() => {
      if (!document.hidden) checkReleaseVersion();
    }, 60000);
  }

  function setupBroadcastImageUpload() {
    const form = document.querySelector('form.broadcast-form');
    if (!form || form.querySelector('input[name="image"]')) return;

    form.enctype = 'multipart/form-data';
    const label = document.createElement('label');
    label.className = 'setting-field broadcast-image';
    label.innerHTML = '<span>Bild (optional)</span><input type="file" name="image" accept="image/jpeg,image/png,image/webp"><small class="muted">JPG, PNG oder WebP · maximal 5 MB. Das Bild erscheint in der App und – wenn unterstützt – direkt in der Push-Mitteilung.</small><img alt="Vorschau des Mitteilungsbildes" hidden style="width:min(100%,420px);max-height:240px;margin-top:10px;border-radius:14px;object-fit:cover;border:1px solid rgba(255,255,255,.1)">';

    const bodyField = form.querySelector('.broadcast-body');
    form.insertBefore(label, bodyField || form.querySelector('button[type="submit"]'));

    const input = label.querySelector('input[name="image"]');
    const preview = label.querySelector('img');
    input.addEventListener('change', () => {
      if (broadcastPreviewUrl) {
        URL.revokeObjectURL(broadcastPreviewUrl);
        broadcastPreviewUrl = null;
      }
      const file = input.files && input.files[0];
      if (!file) {
        preview.hidden = true;
        preview.removeAttribute('src');
        return;
      }
      broadcastPreviewUrl = URL.createObjectURL(file);
      preview.src = broadcastPreviewUrl;
      preview.hidden = false;
    });
  }

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
  window.addEventListener('load', () => {
    registerGrantedPush();
    startReleaseChecks();
    setupBroadcastImageUpload();
  }, { once: true });

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      registerGrantedPush();
      checkReleaseVersion();
    }
  });

  window.addEventListener('pageshow', () => {
    checkReleaseVersion();
    setupBroadcastImageUpload();
  });

  window.addEventListener('pagehide', () => {
    if (releaseCheckTimer) window.clearInterval(releaseCheckTimer);
    if (broadcastPreviewUrl) URL.revokeObjectURL(broadcastPreviewUrl);
  }, { once: true });

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
