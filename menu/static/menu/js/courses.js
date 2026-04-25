/* courses.js — cochage AJAX des articles de la liste de courses */
(function () {
    'use strict';

    const CSRF = document.getElementById('csrf-token')?.value || '';

    // Barre de progression
    const progressFill  = document.querySelector('.courses-progress__fill');
    const progressLabel = document.querySelector('.courses-progress__label');

    function updateProgress() {
        const items   = document.querySelectorAll('.shopping-item');
        const checked = document.querySelectorAll('.shopping-item--checked');
        const total   = items.length;
        const done    = checked.length;
        if (!progressFill || !total) return;
        progressFill.style.width = `${Math.round((done / total) * 100)}%`;
        progressLabel.textContent = `${done} / ${total} articles cochés`;
    }

    document.querySelectorAll('.shopping-item').forEach(item => {
        // Clic souris + touche Espace/Entrée pour l'accessibilité
        item.addEventListener('click', () => toggleItem(item));
        item.addEventListener('keydown', e => {
            if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                toggleItem(item);
            }
        });
    });

    async function toggleItem(item) {
        const id = item.dataset.id;
        // Optimistic UI
        const wasChecked = item.classList.contains('shopping-item--checked');
        applyChecked(item, !wasChecked);

        try {
            const resp = await fetch(`/courses/item/${id}/cocher/`, {
                method:  'POST',
                headers: { 'X-CSRFToken': CSRF },
            });
            const data = await resp.json();
            if (!data.ok) {
                // Rollback
                applyChecked(item, wasChecked);
            } else {
                applyChecked(item, data.checked);
                updateProgress();
            }
        } catch {
            // Rollback réseau
            applyChecked(item, wasChecked);
        }
    }

    function applyChecked(item, checked) {
        item.classList.toggle('shopping-item--checked', checked);
        item.setAttribute('aria-pressed', checked ? 'true' : 'false');
        const checkSpan = item.querySelector('.shopping-item__check');
        if (checkSpan) checkSpan.textContent = checked ? '✓' : '';
    }

})();
