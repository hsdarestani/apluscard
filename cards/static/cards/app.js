if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}

document.addEventListener('click', event => {
  const openButton = event.target.closest('[data-dialog-open]');
  if (openButton) document.getElementById(openButton.dataset.dialogOpen)?.showModal();
  if (event.target.closest('[data-dialog-close]')) event.target.closest('dialog')?.close();

  const tabButton = event.target.closest('[data-tab]');
  if (tabButton) {
    const wrapper = tabButton.closest('.action-panel');
    wrapper?.querySelectorAll('.tab-button').forEach(button => button.classList.toggle('active', button === tabButton));
    wrapper?.querySelectorAll('.tab-content').forEach(panel => panel.classList.toggle('active', panel.id === tabButton.dataset.tab));
  }
});
