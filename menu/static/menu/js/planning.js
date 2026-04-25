/* planning.js — interactions du planning hebdomadaire */
(function () {
    'use strict';

    const meta      = document.getElementById('planning-meta');
    const PLAN_ID   = meta ? meta.dataset.planId   : null;
    const IS_COOK   = meta ? meta.dataset.isCuisinier === 'true' : false;
    const CSRF      = document.getElementById('csrf-token')?.value || '';

    // Repas avec recette (source pour le select "restes de…")
    let mealsAvecRecette = [];
    try {
        mealsAvecRecette = JSON.parse(
            document.getElementById('meals-json')?.textContent || '[]'
        );
    } catch (e) { /* ignore */ }

    // ── Helpers ──────────────────────────────────────────────────────────────

    function debounce(fn, delay) {
        let t;
        return function (...args) {
            clearTimeout(t);
            t = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    async function apiRecettes(q) {
        try {
            const r = await fetch(`/api/recettes/?q=${encodeURIComponent(q)}`);
            const d = await r.json();
            return d.ok ? d.results : [];
        } catch { return []; }
    }

    function makeSearchDropdown(searchInput, resultsList, onSelect) {
        let selected = { id: null, title: '' };

        searchInput.addEventListener('input', debounce(async function () {
            const q = this.value.trim();
            resultsList.innerHTML = '';
            if (q.length < 1) return;
            const results = await apiRecettes(q);
            results.forEach(r => {
                const li = document.createElement('li');
                li.className = 'recipe-search-item';
                li.textContent = r.title;
                if (r.calories_per_serving) {
                    li.textContent += ` — ${Math.round(r.calories_per_serving)} kcal/pers.`;
                }
                li.dataset.id       = r.id;
                li.dataset.title    = r.title;
                li.dataset.servings = r.base_servings;
                li.addEventListener('click', () => {
                    selected = { id: r.id, title: r.title, servings: r.base_servings };
                    resultsList.innerHTML = '';
                    searchInput.value = r.title;
                    onSelect(selected);
                });
                resultsList.appendChild(li);
            });
        }, 300));

        // Fermer en cliquant en dehors
        document.addEventListener('click', e => {
            if (!searchInput.contains(e.target) && !resultsList.contains(e.target)) {
                resultsList.innerHTML = '';
            }
        });

        return {
            clear() { selected = { id: null, title: '' }; searchInput.value = ''; resultsList.innerHTML = ''; },
            getSelected() { return selected; },
            setSelected(id, title) { selected = { id, title }; searchInput.value = title || ''; },
        };
    }

    // ── Dialogue : modifier un repas (Cuisinier) ─────────────────────────────

    if (IS_COOK) {
        const dlg            = document.getElementById('dialog-meal');
        const dlgLabel       = document.getElementById('dialog-meal-label');
        const recipeName     = document.getElementById('meal-recipe-name');
        const servingsInput  = document.getElementById('meal-servings');
        const leftoversCheck = document.getElementById('meal-is-leftovers');
        const sourceSection  = document.getElementById('meal-source-section');
        const sourceSelect   = document.getElementById('meal-source-select');

        const search = makeSearchDropdown(
            document.getElementById('meal-recipe-search'),
            document.getElementById('meal-recipe-results'),
            ({ title }) => { recipeName.textContent = title; recipeName.classList.remove('text-muted'); }
        );

        let currentSlot = {};

        // Ouvrir le dialog en cliquant sur un créneau
        document.querySelectorAll('.meal-slot[data-editable]').forEach(slot => {
            slot.addEventListener('click', function () {
                currentSlot = {
                    date:       this.dataset.date,
                    meal_time:  this.dataset.mealTime,
                    meal_id:    this.dataset.mealId || null,
                    recipe_id:  this.dataset.recipeId || null,
                    recipe_title: this.dataset.recipeTitle || '',
                    servings:   parseInt(this.dataset.servings) || 4,
                    is_leftovers: this.dataset.isLeftovers === 'true',
                };

                // Pré-remplir
                const label = currentSlot.meal_time === 'lunch' ? 'Midi' : 'Soir';
                dlgLabel.textContent = `${currentSlot.date} — ${label}`;

                search.setSelected(currentSlot.recipe_id, currentSlot.recipe_title);
                recipeName.textContent     = currentSlot.recipe_title || 'Aucune recette';
                recipeName.classList.toggle('text-muted', !currentSlot.recipe_title);
                servingsInput.value        = currentSlot.servings;
                leftoversCheck.checked     = currentSlot.is_leftovers;
                sourceSection.style.display = currentSlot.is_leftovers ? 'block' : 'none';

                // Peupler le select "restes de…"
                sourceSelect.innerHTML = '<option value="">— choisir —</option>';
                mealsAvecRecette.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m.id;
                    opt.textContent = m.label;
                    sourceSelect.appendChild(opt);
                });

                dlg.showModal();
            });
        });

        // Vider la recette
        document.getElementById('btn-clear-recipe')?.addEventListener('click', () => {
            search.clear();
            recipeName.textContent = 'Aucune recette';
            recipeName.classList.add('text-muted');
        });

        // Toggle restes
        leftoversCheck.addEventListener('change', function () {
            sourceSection.style.display = this.checked ? 'block' : 'none';
        });

        // Enregistrer
        document.getElementById('btn-save-meal')?.addEventListener('click', async () => {
            const selected = search.getSelected();
            const body = {
                date:           currentSlot.date,
                meal_time:      currentSlot.meal_time,
                recipe_id:      selected.id ? parseInt(selected.id) : null,
                servings_count: parseInt(servingsInput.value) || null,
                is_leftovers:   leftoversCheck.checked,
                source_meal_id: leftoversCheck.checked ? (parseInt(sourceSelect.value) || null) : null,
            };

            try {
                const resp = await fetch(`/planning/${PLAN_ID}/meal/`, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
                    body:    JSON.stringify(body),
                });
                const data = await resp.json();
                if (data.ok) {
                    dlg.close();
                    updateSlotDOM(currentSlot.date, currentSlot.meal_time, data);
                    // Mettre à jour la liste des repas pour le select "restes de…"
                    if (data.recipe_id && !mealsAvecRecette.find(m => m.id === data.meal_id)) {
                        const label = `${currentSlot.date} ${body.meal_time === 'lunch' ? 'Midi' : 'Soir'} — ${data.recipe_title}`;
                        mealsAvecRecette.push({ id: data.meal_id, label });
                    }
                } else {
                    alert(`Erreur : ${data.error}`);
                }
            } catch {
                alert('Erreur de connexion. Réessayez.');
            }
        });

        document.getElementById('btn-cancel-meal')?.addEventListener('click', () => dlg.close());
    }

    // ── Mise à jour du DOM après sauvegarde ──────────────────────────────────

    function updateSlotDOM(dateStr, mealTime, data) {
        const slot = document.querySelector(
            `.meal-slot[data-date="${dateStr}"][data-meal-time="${mealTime}"]`
        );
        if (!slot) return;

        // Mettre à jour les data attrs
        slot.dataset.mealId      = data.meal_id  || '';
        slot.dataset.recipeId    = data.recipe_id    || '';
        slot.dataset.recipeTitle = data.recipe_title || '';
        slot.dataset.servings    = data.servings_count || '';
        slot.dataset.isLeftovers = data.is_leftovers ? 'true' : 'false';

        // Mettre à jour l'affichage
        const body = slot.querySelector('.meal-slot__body');
        if (!body) return;

        if (data.recipe_title) {
            slot.classList.add('meal-slot--filled');
            const leftBadge = data.is_leftovers
                ? '<span class="badge badge--leftovers">Restes</span>' : '';
            const servings = data.servings_count
                ? `<span>${data.servings_count} pers.</span>` : '';
            body.innerHTML = `
                <span class="meal-slot__recipe">${escHtml(data.recipe_title)}</span>
                <div class="meal-slot__meta">${servings}${leftBadge}</div>`;
        } else {
            slot.classList.remove('meal-slot--filled', 'meal-slot--leftovers');
            body.innerHTML = '<span class="meal-slot__empty">+ Ajouter</span>';
        }

        if (data.is_leftovers) {
            slot.classList.add('meal-slot--leftovers');
        } else {
            slot.classList.remove('meal-slot--leftovers');
        }
    }

    function escHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ── Dialogue : proposer une recette (Convive) ─────────────────────────────

    if (!IS_COOK) {
        const dlg    = document.getElementById('dialog-propose');
        const btnOpen  = document.getElementById('btn-propose');
        const recipeName = document.getElementById('propose-recipe-name');

        let proposeSelected = { id: null, title: '' };

        const search = makeSearchDropdown(
            document.getElementById('propose-recipe-search'),
            document.getElementById('propose-recipe-results'),
            ({ id, title }) => {
                proposeSelected = { id, title };
                recipeName.textContent = title;
                recipeName.classList.remove('text-muted');
            }
        );

        btnOpen?.addEventListener('click', () => {
            proposeSelected = { id: null, title: '' };
            search.clear();
            recipeName.textContent = 'Aucune recette sélectionnée';
            recipeName.classList.add('text-muted');
            document.getElementById('propose-message').value = '';
            dlg.showModal();
        });

        document.getElementById('btn-submit-propose')?.addEventListener('click', async () => {
            if (!proposeSelected.id) {
                alert('Veuillez sélectionner une recette.');
                return;
            }
            const body = {
                recipe_id: parseInt(proposeSelected.id),
                message:   document.getElementById('propose-message').value.trim() || null,
            };
            try {
                const resp = await fetch(`/planning/${PLAN_ID}/proposer/`, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
                    body:    JSON.stringify(body),
                });
                const data = await resp.json();
                if (data.ok) {
                    dlg.close();
                    // Confirmation dans l'UI plutôt qu'une alerte
                    showFlash(`✅ Proposition envoyée : "${data.recipe_title}"`, 'success');
                    // Ajouter à "Mes propositions" sans rechargement
                    appendUserProposal(data.proposal_id, data.recipe_title, body.message);
                } else {
                    alert(`Erreur : ${data.error}`);
                }
            } catch {
                alert('Erreur de connexion. Réessayez.');
            }
        });

        document.getElementById('btn-cancel-propose')?.addEventListener('click', () => dlg.close());

        // ── Annuler ma proposition (Convive) ─────────────────────────────
        document.addEventListener('click', async e => {
            const btn = e.target.closest('.btn-cancel-my-proposal');
            if (!btn) return;
            const pid = btn.dataset.proposalId;
            if (!confirm('Annuler cette proposition ?')) return;
            await deleteProposal(pid, `user-proposal-${pid}`, 'user-proposals-empty',
                'user-proposals-list', 'Tu n\'as pas encore proposé de recette cette semaine.');
        });
    }

    // ── Cuisinier : Placer / Ignorer des propositions ─────────────────────

    if (IS_COOK) {

        // Placer une proposition dans un créneau
        document.addEventListener('click', async e => {
            const btn = e.target.closest('.btn-place-proposal');
            if (!btn) return;

            const li     = btn.closest('.proposals-list__item');
            const select = li?.querySelector('.proposal-slot-select');
            if (!select?.value) {
                alert('Choisissez un créneau dans la liste déroulante.');
                return;
            }

            const [dateStr, mealTime] = select.value.split('__');
            const recipeId    = parseInt(btn.dataset.recipeId, 10);
            const recipeTitle = btn.dataset.recipeTitle;
            const proposalId  = btn.dataset.proposalId;

            const body = {
                date:           dateStr,
                meal_time:      mealTime,
                recipe_id:      recipeId,
                servings_count: null,
                is_leftovers:   false,
                source_meal_id: null,
            };

            btn.disabled = true;
            try {
                const resp = await fetch(`/planning/${PLAN_ID}/meal/`, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
                    body:    JSON.stringify(body),
                });
                const data = await resp.json();
                if (data.ok) {
                    updateSlotDOM(dateStr, mealTime, data);
                    // Supprimer la proposition placée
                    await deleteProposal(proposalId, `proposal-${proposalId}`, 'proposals-empty',
                        'proposals-list', 'Aucune proposition pour cette semaine.');
                    updateProposalCount(-1);
                    showFlash(`✅ "${recipeTitle}" placé dans le planning.`, 'success');
                } else {
                    btn.disabled = false;
                    alert(`Erreur : ${data.error}`);
                }
            } catch {
                btn.disabled = false;
                alert('Erreur de connexion.');
            }
        });

        // Ignorer une proposition
        document.addEventListener('click', async e => {
            const btn = e.target.closest('.btn-ignore-proposal');
            if (!btn) return;
            const pid = btn.dataset.proposalId;
            if (!confirm('Ignorer cette proposition ?')) return;
            const ok = await deleteProposal(pid, `proposal-${pid}`, 'proposals-empty',
                'proposals-list', 'Aucune proposition pour cette semaine.');
            if (ok) updateProposalCount(-1);
        });
    }

    // ── Helpers propositions ──────────────────────────────────────────────

    async function deleteProposal(proposalId, liId, emptyId, listId, emptyText) {
        try {
            const resp = await fetch(`/planning/proposition/${proposalId}/supprimer/`, {
                method: 'POST', headers: { 'X-CSRFToken': CSRF },
            });
            const data = await resp.json();
            if (data.ok) {
                const li   = document.getElementById(liId);
                const list = document.getElementById(listId);
                if (li) li.remove();
                if (list && list.children.length === 0) {
                    const empty = document.createElement('p');
                    empty.id        = emptyId;
                    empty.className = 'text-muted';
                    empty.textContent = emptyText;
                    list.parentNode.insertBefore(empty, list);
                    list.remove();
                }
                return true;
            }
        } catch { /* silencieux */ }
        return false;
    }

    function updateProposalCount(delta) {
        const el = document.getElementById('proposals-count');
        if (!el) return;
        const m = el.textContent.match(/\d+/);
        const n = m ? parseInt(m[0], 10) + delta : 0;
        el.textContent = n > 0 ? `(${n})` : '';
    }

    function appendUserProposal(proposalId, recipeTitle, message) {
        const list     = document.getElementById('user-proposals-list');
        const emptyEl  = document.getElementById('user-proposals-empty');
        const section  = document.getElementById('user-proposals-section');
        if (!section) return;

        // Créer la liste si elle n'existe pas encore
        let ul = list;
        if (!ul) {
            ul = document.createElement('ul');
            ul.className = 'proposals-list';
            ul.id        = 'user-proposals-list';
            if (emptyEl) { emptyEl.replaceWith(ul); } else { section.appendChild(ul); }
        }

        const li = document.createElement('li');
        li.className = 'proposals-list__item';
        li.id        = `user-proposal-${proposalId}`;
        li.innerHTML = `
            <div class="proposals-list__header">
                <span class="proposals-list__recipe">${escHtml(recipeTitle)}</span>
                <span class="proposals-list__date text-muted">Aujourd'hui</span>
            </div>
            ${message ? `<p class="proposals-list__msg">${escHtml(message)}</p>` : ''}
            <div class="proposals-list__actions">
                <button type="button" class="btn-cancel-my-proposal btn btn--secondary btn--sm"
                        data-proposal-id="${proposalId}">
                    ✕ Annuler ma proposition
                </button>
            </div>`;
        ul.insertBefore(li, ul.firstChild);
    }

    function showFlash(message, type) {
        const existing = document.getElementById('planning-flash');
        if (existing) existing.remove();
        const div = document.createElement('div');
        div.id        = 'planning-flash';
        div.className = `message message--${type === 'success' ? 'success' : 'error'}`;
        div.textContent = message;
        div.style.cssText = 'position:fixed;top:1rem;left:50%;transform:translateX(-50%);z-index:9999;max-width:90vw;';
        document.body.appendChild(div);
        setTimeout(() => div.remove(), 3500);
    }

})();
