(function () {
  function nativePlatform() {
    const platform = window.Capacitor?.getPlatform?.() || window.Capacitor?.platform || '';
    return String(platform).toLowerCase();
  }

  function nativeCameraPlugin() {
    return window.Capacitor?.Plugins?.Camera || null;
  }

  async function requestNativeCameraPermission() {
    const platform = nativePlatform();
    const plugin = nativeCameraPlugin();

    if (!plugin || !['ios', 'android'].includes(platform)) {
      return { state: 'web', platform };
    }

    let permissions = await plugin.checkPermissions();
    let state = permissions?.camera || 'prompt';

    if (state === 'prompt' || state === 'prompt-with-rationale') {
      permissions = await plugin.requestPermissions({ permissions: ['camera'] });
      state = permissions?.camera || state;
    }

    return { state, platform };
  }

  async function prepareForScanner() {
    try {
      const permission = await requestNativeCameraPermission();
      if (permission.state === 'web' || permission.state === 'granted') {
        return { allowed: true, ...permission };
      }
      return { allowed: false, ...permission };
    } catch (error) {
      console.error('Native camera permission request failed', error);
      return { allowed: false, state: 'error', platform: nativePlatform(), error };
    }
  }

  window.SamsCameraPermissions = {
    prepareForScanner,
    requestNativeCameraPermission
  };
})();
