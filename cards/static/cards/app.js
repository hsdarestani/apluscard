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

// The interface behaves like an installed app. Prevent accidental pinch and
// double-tap zoom without running a continuous animation or polling loop.
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
