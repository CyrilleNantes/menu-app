/* notation.js — Sélecteur d'étoiles + soumission AJAX */
(function () {
    'use strict';

    const detail    = document.getElementById('recette-detail');
    const RECIPE_ID = detail ? detail.dataset.recipeId : null;
    const CSRF      = document.getElementById('csrf-token')?.value || '';

    if (!RECIPE_ID) return;

    // ── Sélecteur d'étoiles ───────────────────────────────────────────────

    const starsInput  = document.getElementById('stars-value');
    const btnNoter    = document.getElementById('btn-noter');
    const starBtns    = Array.from(document.querySelectorAll('.star-btn'));

    let selectedStars = 0;

    function paintStars(upTo) {
        starBtns.forEach((btn, i) => {
            btn.classList.toggle('star-btn--on', i < upTo);
        });
    }

    starBtns.forEach((btn, index) => {
        // Survol
        btn.addEventListener('mouseenter', () => paintStars(index + 1));
        btn.addEventListener('mouseleave', () => paintStars(selectedStars));

        // Sélection
        btn.addEventListener('click', () => {
            selectedStars = index + 1;
            starsInput.value = selectedStars;
            paintStars(selectedStars);
            if (btnNoter) btnNoter.disabled = false;
        });

        // Accessibilité clavier
        btn.addEventListener('keydown', e => {
            if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                selectedStars = index + 1;
                starsInput.value = selectedStars;
                paintStars(selectedStars);
                if (btnNoter) btnNoter.disabled = false;
            }
        });
    });

    // ── Envoi AJAX ────────────────────────────────────────────────────────

    btnNoter?.addEventListener('click', async () => {
        const stars   = parseInt(starsInput.value, 10);
        const comment = document.getElementById('noter-comment')?.value.trim() || '';

        if (!stars || stars < 1 || stars > 5) return;

        btnNoter.disabled    = true;
        btnNoter.textContent = 'Envoi…';

        try {
            const resp = await fetch(`/recettes/${RECIPE_ID}/noter/`, {
                method:  'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken':  CSRF,
                },
                body: JSON.stringify({ stars, comment: comment || null }),
            });
            const data = await resp.json();

            if (data.ok) {
                // Masquer le formulaire, montrer confirmation
                document.getElementById('noter-form-wrap').style.display = 'none';
                document.getElementById('noter-confirm').style.display   = '';

                // Mettre à jour la note moyenne dans l'en-tête
                updateNoteDisplay(data.new_average, data.review_count);

                // Insérer le nouvel avis en tête de liste
                prependReview(data.review);
            } else {
                btnNoter.disabled    = false;
                btnNoter.textContent = 'Envoyer mon avis';
                alert(`Erreur : ${data.error}`);
            }
        } catch {
            btnNoter.disabled    = false;
            btnNoter.textContent = 'Envoyer mon avis';
            alert('Erreur de connexion. Réessayez.');
        }
    });

    // ── Mise à jour de la note moyenne ────────────────────────────────────

    function updateNoteDisplay(avg, count) {
        const starsEl = document.getElementById('note-stars');
        const nbAvisEls = document.querySelectorAll('#nb-avis, #nb-avis-titre');

        if (starsEl) {
            let html = '';
            for (let i = 1; i <= 5; i++) {
                html += i <= Math.round(avg) ? '★' : '☆';
            }
            starsEl.textContent = html;
        }

        nbAvisEls.forEach(el => { el.textContent = count; });

        const noteText = document.getElementById('note-text');
        if (noteText) {
            noteText.innerHTML = `${avg}/5 — <span id="nb-avis">${count}</span> avis`;
        }
    }

    // ── Insertion du nouvel avis dans la liste ────────────────────────────

    function prependReview(review) {
        const list    = document.getElementById('avis-list');
        const emptyEl = document.getElementById('avis-empty');
        if (!list) return;

        if (emptyEl) emptyEl.remove();

        const li = document.createElement('li');
        li.className = 'avis-item avis-item--new';
        li.innerHTML = `
            <div class="avis-item__header">
                <span class="avis-item__user">${escHtml(review.user)}</span>
                <span class="avis-item__stars stars">${starsHtml(review.stars)}</span>
                <span class="avis-item__date text-muted">${escHtml(review.date)}</span>
            </div>
            ${review.comment ? `<p class="avis-item__comment">${escHtml(review.comment)}</p>` : ''}
        `;
        list.insertBefore(li, list.firstChild);
    }

    function starsHtml(n) {
        let s = '';
        for (let i = 1; i <= 5; i++) s += i <= n ? '★' : '☆';
        return s;
    }

    function escHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

})();
