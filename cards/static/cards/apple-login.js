(() => {
  const button = document.getElementById('apple-login-button');
  if (!button) return;

  const status = document.getElementById('apple-login-status');
  const capacitor = window.Capacitor || null;
  const platform = String(capacitor?.getPlatform?.() || capacitor?.platform || '').toLowerCase();
  const plugin = capacitor?.Plugins?.AppleSignIn || null;
  const nativeEndpoint = button.dataset.nativeUrl || '';
  const webLoginUrl = button.dataset.webUrl || '';
  let busy = false;

  function setStatus(message, isError = false) {
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('error', Boolean(message && isError));
  }

  function setBusy(value) {
    busy = value;
    button.disabled = value;
    button.setAttribute('aria-busy', value ? 'true' : 'false');
    button.classList.toggle('is-loading', value);
  }

  function randomNonce() {
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  }

  function csrfToken() {
    return document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '';
  }

  function isCancelled(error) {
    const value = `${error?.code || ''} ${error?.message || error || ''}`.toUpperCase();
    return value.includes('CANCEL') || value.includes('1001');
  }

  button.addEventListener('click', async () => {
    if (busy) return;

    if (platform !== 'ios') {
      if (webLoginUrl) window.location.assign(webLoginUrl);
      return;
    }

    if (!plugin?.signIn || !nativeEndpoint) {
      setStatus('Die native Apple-Anmeldung ist in dieser App-Version nicht verfügbar.', true);
      return;
    }

    const nonce = randomNonce();
    setBusy(true);
    setStatus('Apple-Anmeldung wird geöffnet …');

    try {
      const credential = await plugin.signIn({
        scopes: ['EMAIL', 'FULL_NAME'],
        nonce,
      });

      const response = await fetch(nativeEndpoint, {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken(),
        },
        body: JSON.stringify({
          authorizationCode: credential.authorizationCode,
          idToken: credential.idToken,
          user: credential.user,
          email: credential.email,
          givenName: credential.givenName,
          familyName: credential.familyName,
          realUserStatus: credential.realUserStatus,
          nonce,
        }),
      });

      let payload = {};
      try {
        payload = await response.json();
      } catch (_) {}

      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || 'Die Apple-Anmeldung konnte nicht abgeschlossen werden.');
      }

      setStatus('Anmeldung erfolgreich. Du wirst weitergeleitet …');
      window.location.replace(payload.redirect || '/dashboard/');
    } catch (error) {
      if (isCancelled(error)) {
        setStatus('');
      } else {
        console.error('Native Apple sign-in failed', error);
        setStatus(error?.message || 'Die Apple-Anmeldung konnte nicht abgeschlossen werden.', true);
      }
    } finally {
      setBusy(false);
    }
  });
})();
