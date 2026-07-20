if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}

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

if ('IntersectionObserver' in window) {
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
    element.style.transition = `opacity .45s ease ${index * 45}ms, transform .45s ease ${index * 45}ms`;
    observer.observe(element);
  });
}
