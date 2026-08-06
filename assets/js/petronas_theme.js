function hidePetronasLoader() {
  const loader = document.getElementById('petronas-loader');
  if (loader) loader.classList.add('is-hidden');
  const shell = document.getElementById('petronas-shell');
  if (shell) shell.classList.add('is-hidden');
  document.body.classList.add('petronas-ready');
}

// Expose to window so Python can call it via injected script
window.petronasHideLoader = hidePetronasLoader;

document.addEventListener('DOMContentLoaded', () => {
  // Fallback automatic hide in case the app is ready quickly
  window.setTimeout(() => hidePetronasLoader(), 900);


  const enhanceButtons = () => {
    document.querySelectorAll('button').forEach((button) => {
      if (button.dataset.petronasEnhanced === 'true') {
        return;
      }
      button.dataset.petronasEnhanced = 'true';
      button.addEventListener('click', () => {
        button.classList.add('petronas-button-pressed');
        window.setTimeout(() => button.classList.remove('petronas-button-pressed'), 220);
      });
    });
  };

  enhanceButtons();

  const observer = new MutationObserver(() => enhanceButtons());
  observer.observe(document.body, { childList: true, subtree: true });
});
