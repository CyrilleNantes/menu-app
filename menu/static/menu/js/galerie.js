/* galerie.js — carousel photos recette (vanilla JS) */
(function () {
    'use strict';

    const carousel = document.getElementById('galerie-carousel');
    if (!carousel) return;

    const track  = document.getElementById('galerie-track');
    const slides = Array.from(track?.querySelectorAll('.galerie-slide') || []);
    if (slides.length <= 1) return;

    const btnPrev = document.getElementById('galerie-prev');
    const btnNext = document.getElementById('galerie-next');
    const dots    = Array.from(document.querySelectorAll('.galerie-dot'));

    let current = 0;

    function goTo(index) {
        current = (index + slides.length) % slides.length;

        // Décaler la track
        track.style.transform = `translateX(-${current * 100}%)`;

        // Mettre à jour les dots
        dots.forEach((d, i) => {
            d.classList.toggle('galerie-dot--active', i === current);
        });

        // Accessibilité
        slides.forEach((s, i) => {
            s.setAttribute('aria-hidden', i !== current ? 'true' : 'false');
        });
    }

    // Initialisation
    slides.forEach((s, i) => {
        if (i !== 0) s.setAttribute('aria-hidden', 'true');
    });

    btnPrev?.addEventListener('click', () => goTo(current - 1));
    btnNext?.addEventListener('click', () => goTo(current + 1));

    // Clic sur un dot
    dots.forEach(d => {
        d.addEventListener('click', () => goTo(parseInt(d.dataset.index, 10)));
    });

    // Swipe tactile
    let touchStartX = null;
    carousel.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].clientX;
    }, { passive: true });
    carousel.addEventListener('touchend', e => {
        if (touchStartX === null) return;
        const delta = e.changedTouches[0].clientX - touchStartX;
        if (Math.abs(delta) > 40) goTo(delta < 0 ? current + 1 : current - 1);
        touchStartX = null;
    });
})();
