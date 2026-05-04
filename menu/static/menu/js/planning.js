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

        // Écoute l'événement émis par "Utiliser" dans le dialog suggestions
        document.getElementById('meal-recipe-search')?.addEventListener('suggestion-select', e => {
            search.setSelected(e.detail.id, e.detail.title);
        });

        let currentSlot = {};

        // Ouvrir le dialog en cliquant sur un créneau
        document.querySelectorAll('.meal-slot[data-editable]').forEach(slot => {
            slot.addEventListener('click', function () {
                // Ne pas ouvrir le dialog si le créneau est absent (géré par btn-unabsent)
                if (this.dataset.absent === 'true') return;
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
                    // Réafficher les alertes d'équilibre (le menu a changé)
                    if (typeof window._resetAlertesDismissed === 'function') {
                        window._resetAlertesDismissed();
                    }
                    // Rafraîchir le bilan
                    refreshBilan();
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

        const body = slot.querySelector('.meal-slot__body');
        if (!body) return;

        // ── Créneau marqué absent ──────────────────────────────────────────
        if (data.absent === true) {
            slot.dataset.absent = 'true';
            slot.dataset.recipeId    = '';
            slot.dataset.recipeTitle = '';
            slot.dataset.isLeftovers = 'false';
            slot.classList.remove('meal-slot--filled', 'meal-slot--leftovers');
            slot.classList.add('meal-slot--absent');
            body.innerHTML = `
                <span class="meal-slot__absent-label">🏠 Absent</span>
                <button type="button" class="btn-unabsent btn btn--ghost btn--xs"
                        data-date="${dateStr}"
                        data-meal-time="${mealTime}"
                        title="Annuler l'absence">✕</button>`;
            refreshBilan();
            return;
        }

        // ── Absence levée ou recette normale ──────────────────────────────
        slot.dataset.absent      = 'false';
        slot.dataset.mealId      = data.meal_id  || '';
        slot.dataset.recipeId    = data.recipe_id    || '';
        slot.dataset.recipeTitle = data.recipe_title || '';
        slot.dataset.servings    = data.servings_count || '';
        slot.dataset.isLeftovers = data.is_leftovers ? 'true' : 'false';
        slot.classList.remove('meal-slot--absent');

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
            body.innerHTML = `
                <span class="meal-slot__empty">+ Ajouter</span>
                <div class="meal-slot__empty-actions">
                    <button type="button" class="btn-suggestions btn btn--ghost btn--xs"
                            data-date="${dateStr}" data-meal-time="${mealTime}"
                            title="Suggestions">💡</button>
                    <button type="button" class="btn-absent btn btn--ghost btn--xs"
                            data-date="${dateStr}" data-meal-time="${mealTime}"
                            title="Personne ne mange à la maison">🏠</button>
                </div>`;
        }

        if (data.is_leftovers) {
            slot.classList.add('meal-slot--leftovers');
        } else {
            slot.classList.remove('meal-slot--leftovers');
        }

        refreshBilan();
    }

    // ── Bilan : refresh AJAX ──────────────────────────────────────────────────

    async function refreshBilan() {
        const bilanEl = document.getElementById('planning-bilan');
        if (!bilanEl || !PLAN_ID) return;
        try {
            const resp = await fetch(`/planning/${PLAN_ID}/bilan/`, {
                headers: { 'X-CSRFToken': CSRF },
            });
            const data = await resp.json();
            if (!data.ok) return;
            const b = data.bilan;

            // Variété
            _bilanSetItem(bilanEl, 'bilan-fish',     b.fish_count,     b.fish_ok,     'bilan-item--ok', 'bilan-item--warn');
            _bilanSetItem(bilanEl, 'bilan-veg',      b.veg_count,      b.veg_ok,      'bilan-item--ok', 'bilan-item--warn');
            _bilanSetItem(bilanEl, 'bilan-red-meat',  b.red_meat_count, b.red_meat_ok, 'bilan-item--ok', 'bilan-item--warn');

            // Absent
            const absentEl = bilanEl.querySelector('#bilan-absent');
            if (absentEl) absentEl.textContent = b.absent_count;

            // Nutrition
            if (bilanEl.querySelector('#bilan-cal')) {
                bilanEl.querySelector('#bilan-cal').textContent = b.cal_total;
            }
            if (bilanEl.querySelector('#bilan-prot')) {
                bilanEl.querySelector('#bilan-prot').textContent = b.prot_total;
            }

            // Barres de progression
            bilanEl.querySelectorAll('.bilan-progress__bar').forEach(bar => {
                const isCalBar  = bar.closest('.bilan-item')?.querySelector('#bilan-cal');
                const isProtBar = bar.closest('.bilan-item')?.querySelector('#bilan-prot');
                if (isCalBar) {
                    bar.style.width = `${Math.min(b.cal_pct, 100)}%`;
                    bar.className = `bilan-progress__bar bilan-progress__bar--${b.cal_status}`;
                } else if (isProtBar) {
                    bar.style.width = `${Math.min(b.prot_pct, 100)}%`;
                    bar.className = `bilan-progress__bar bilan-progress__bar--${b.prot_status}`;
                }
            });
        } catch { /* silencieux — le bilan se mettra à jour au prochain chargement */ }
    }

    function _bilanSetItem(container, valueId, count, isOk, okClass, warnClass) {
        const el = container.querySelector(`#${valueId}`);
        if (el) el.textContent = count;
        const item = el?.closest('.bilan-item');
        if (item) {
            item.classList.toggle(okClass,   isOk);
            item.classList.toggle(warnClass, !isOk);
        }
    }

    // ── Absent toggle (Cuisinier) ─────────────────────────────────────────────

    if (IS_COOK) {
        // Marquer un créneau absent
        document.addEventListener('click', async e => {
            const btn = e.target.closest('.btn-absent');
            if (!btn) return;
            e.stopPropagation();
            const dateStr  = btn.dataset.date;
            const mealTime = btn.dataset.mealTime;
            try {
                const resp = await fetch(`/planning/${PLAN_ID}/meal/`, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
                    body:    JSON.stringify({ date: dateStr, meal_time: mealTime, absent: true }),
                });
                const data = await resp.json();
                if (data.ok) {
                    updateSlotDOM(dateStr, mealTime, data);
                    if (typeof window._resetAlertesDismissed === 'function') {
                        window._resetAlertesDismissed();
                    }
                }
            } catch { /* silencieux */ }
        });

        // Annuler l'absence
        document.addEventListener('click', async e => {
            const btn = e.target.closest('.btn-unabsent');
            if (!btn) return;
            e.stopPropagation();
            const dateStr  = btn.dataset.date;
            const mealTime = btn.dataset.mealTime;
            try {
                const resp = await fetch(`/planning/${PLAN_ID}/meal/`, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
                    body:    JSON.stringify({ date: dateStr, meal_time: mealTime, absent: false }),
                });
                const data = await resp.json();
                if (data.ok) {
                    updateSlotDOM(dateStr, mealTime, data);
                }
            } catch { /* silencieux */ }
        });
    }

    function escHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ── Alertes équilibre — dismiss via sessionStorage ───────────────────────

    (function initAlertes() {
        const container = document.getElementById('alertes-planning');
        if (!container) return;

        const planId    = container.dataset.planId;
        const storageKey = `dismissed_alertes_${planId}`;

        function getDismissed() {
            try { return JSON.parse(sessionStorage.getItem(storageKey) || '[]'); }
            catch { return []; }
        }

        function saveDismissed(arr) {
            sessionStorage.setItem(storageKey, JSON.stringify(arr));
        }

        // Masquer les alertes déjà ignorées au chargement de la page
        const dismissed = getDismissed();
        container.querySelectorAll('.planning-alerte').forEach(el => {
            if (dismissed.includes(el.dataset.type)) {
                el.style.display = 'none';
            }
        });

        // Bouton ✕ — dismiss
        container.addEventListener('click', e => {
            const btn = e.target.closest('.planning-alerte__dismiss');
            if (!btn) return;
            const alerte = btn.closest('.planning-alerte');
            if (!alerte) return;
            const type = alerte.dataset.type;
            const arr  = getDismissed();
            if (!arr.includes(type)) arr.push(type);
            saveDismissed(arr);
            alerte.style.display = 'none';
        });

        // Exposer une fonction pour réafficher les alertes après modification d'un repas
        window._resetAlertesDismissed = function () {
            saveDismissed([]);
            container.querySelectorAll('.planning-alerte').forEach(el => {
                el.style.display = '';
            });
        };
    })();

    // ── Dialogue : suggestions de recettes (Cuisinier) ──────────────────────

    if (IS_COOK) {
        const dlgSug      = document.getElementById('dialog-suggestions');
        const sugLabel    = document.getElementById('suggestions-label');
        const sugLoading  = document.getElementById('suggestions-loading');
        const sugEmpty    = document.getElementById('suggestions-empty');
        const sugList     = document.getElementById('suggestions-list');

        const REASON_ICONS = {
            rotation:  { icon: '🔄', label: 'Rotation' },
            famille:   { icon: '⭐', label: 'Avis famille' },
            variete:   { icon: '🥩', label: 'Variété' },
            saison:    { icon: '🌿', label: 'Saison' },
            nutrition: { icon: '⚖️', label: 'Protéines' },
        };

        // Données WPD mémorisées entre les appels (rafraîchi à chaque dialog)
        let _lastWpd = 1.0;

        // Clic sur le bouton 💡 d'un créneau vide
        document.addEventListener('click', async e => {
            const btn = e.target.closest('.btn-suggestions');
            if (!btn) return;
            e.stopPropagation(); // ne pas ouvrir le dialog repas

            const dateStr  = btn.dataset.date;
            const mealTime = btn.dataset.mealTime;
            const label    = mealTime === 'lunch' ? 'Midi' : 'Soir';
            sugLabel.textContent = `${dateStr} — ${label}`;

            // Réinitialiser l'état du dialog
            sugList.innerHTML    = '';
            sugEmpty.style.display   = 'none';
            sugLoading.style.display = 'block';
            dlgSug.showModal();

            try {
                const url  = `/planning/${PLAN_ID}/suggestions/?date=${dateStr}&meal_time=${mealTime}`;
                const resp = await fetch(url, { headers: { 'X-CSRFToken': CSRF } });
                const data = await resp.json();

                sugLoading.style.display = 'none';

                if (!data.ok || !data.suggestions?.length) {
                    sugEmpty.style.display = 'block';
                    return;
                }

                // Mémoriser WPD pour les tooltips enrichis
                _lastWpd = data.wpd || 1.0;

                // ── Bandeau déficit protéique ────────────────────────────────
                const existingBanner = dlgSug.querySelector('.sug-deficit-banner');
                if (existingBanner) existingBanner.remove();
                if (data.deficit_proteique) {
                    const banner = document.createElement('p');
                    banner.className = 'sug-deficit-banner';
                    banner.textContent = '⚖️ Semaine en déficit protéique — les recettes riches en protéines sont mises en avant';
                    sugList.before(banner);
                }

                data.suggestions.forEach(s => {
                    const scorePercent = Math.round(s.score * 100);

                    // ── Icônes de justification ──────────────────────────────
                    const reasonsHtml = Object.entries(s.reasons)
                        .sort((a, b) => b[1] - a[1])
                        .map(([key, val]) => {
                            const r = REASON_ICONS[key] || { icon: '?', label: key };
                            const opacity = val < 0.3 ? 'sug-reason--low' : val >= 0.7 ? 'sug-reason--high' : '';
                            // Tooltip enrichi pour la dimension nutrition si WPD > 1.0
                            let tooltip = `${r.label} : ${Math.round(val * 100)}%`;
                            if (key === 'nutrition' && _lastWpd > 1.0 && s.proteins_per_serving) {
                                tooltip = `⚖️ Cette recette apporte ${s.proteins_per_serving}g de protéines — utile cette semaine`;
                            }
                            return `<span class="sug-reason ${opacity}" title="${escHtml(tooltip)}">${r.icon}</span>`;
                        }).join('');

                    // ── Indicateur protéines ─────────────────────────────────
                    const protIcons = { élevé: '🥩🥩🥩', correct: '🥩🥩', faible: '🥩', inconnu: '🥩' };
                    const protClass = { élevé: 'sug-prot--high', correct: 'sug-prot--mid', faible: 'sug-prot--low', inconnu: 'sug-prot--unknown' };
                    const lvl    = s.protein_level || 'inconnu';
                    const protGr = s.proteins_per_serving != null ? `${s.proteins_per_serving}g` : '?';
                    const protHtml = `<span class="sug-prot ${protClass[lvl]}" title="Protéines par portion">${protIcons[lvl]} ${protGr}</span>`;

                    const li = document.createElement('li');
                    li.className = 'sug-item';
                    li.innerHTML = `
                        <div class="sug-item__main">
                            <span class="sug-item__title">${escHtml(s.title)}</span>
                            <span class="sug-item__score">${scorePercent}%</span>
                        </div>
                        <div class="sug-item__meta">${protHtml}<div class="sug-item__reasons">${reasonsHtml}</div></div>
                        <button type="button"
                                class="btn btn--primary btn--sm btn-use-suggestion"
                                data-recipe-id="${s.recipe_id}"
                                data-recipe-title="${escHtml(s.title)}"
                                data-date="${dateStr}"
                                data-meal-time="${mealTime}">
                            Utiliser
                        </button>`;
                    sugList.appendChild(li);
                });

            } catch {
                sugLoading.style.display = 'none';
                sugEmpty.style.display   = 'block';
                sugEmpty.textContent     = 'Erreur lors du chargement des suggestions.';
            }
        });

        // Sélectionner une suggestion → pré-remplir le dialog repas
        document.addEventListener('click', e => {
            const btn = e.target.closest('.btn-use-suggestion');
            if (!btn) return;

            dlgSug.close();

            // Simuler l'ouverture du dialog repas avec cette recette pré-sélectionnée
            const slot = document.querySelector(
                `.meal-slot[data-date="${btn.dataset.date}"][data-meal-time="${btn.dataset.mealTime}"]`
            );
            if (slot) {
                // Déclencher le click sur le slot pour ouvrir le dialog repas
                slot.click();
                // Puis pré-remplir la recette après ouverture (micro-délai pour le showModal)
                setTimeout(() => {
                    const recipeSearch = document.getElementById('meal-recipe-search');
                    const recipeName   = document.getElementById('meal-recipe-name');
                    if (recipeSearch && recipeName) {
                        recipeSearch.value  = btn.dataset.recipeTitle;
                        recipeName.textContent = btn.dataset.recipeTitle;
                        recipeName.classList.remove('text-muted');
                        // Mettre à jour l'état interne du search helper via un événement custom
                        recipeSearch.dispatchEvent(new CustomEvent('suggestion-select', {
                            detail: { id: btn.dataset.recipeId, title: btn.dataset.recipeTitle }
                        }));
                    }
                }, 50);
            }
        });

        document.getElementById('btn-cancel-suggestions')?.addEventListener('click', () => dlgSug.close());
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

// ── Présence ────────────────────────────────────────────────────────────────
(function () {
    const meta = document.getElementById('planning-meta');
    if (!meta) return;
    const presenceUrl = meta.dataset.presenceUrl;
    if (!presenceUrl) return;

    const csrf = document.getElementById('csrf-token')?.value || '';

    function getMemberIds() {
        return [...document.querySelectorAll('.presence-member-cb:checked')]
            .map(cb => parseInt(cb.dataset.userId, 10));
    }

    function getGuests() {
        return [...document.querySelectorAll('.presence-guest-tag')]
            .map(tag => tag.childNodes[0].textContent.trim())
            .filter(Boolean);
    }

    function savePresence() {
        fetch(presenceUrl, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf, 'Content-Type': 'application/json' },
            body: JSON.stringify({ member_ids: getMemberIds(), guests: getGuests() }),
        }).catch(() => {});
    }

    // Membres famille
    document.querySelectorAll('.presence-toggle').forEach(label => {
        label.addEventListener('click', function (e) {
            e.preventDefault();
            const cb = label.querySelector('.presence-member-cb');
            cb.checked = !cb.checked;
            label.classList.toggle('presence-toggle--active', cb.checked);
            savePresence();
        });
    });

    // Invités — ajout via Entrée
    const guestInput = document.getElementById('presence-guest-input');
    const guestContainer = document.getElementById('presence-guests');

    function addGuestTag(name) {
        const span = document.createElement('span');
        span.className = 'presence-guest-tag';
        span.innerHTML = `${name} <button type="button" class="presence-guest-remove" data-name="${name}" aria-label="Supprimer">✕</button>`;
        span.querySelector('.presence-guest-remove').addEventListener('click', function () {
            span.remove();
            savePresence();
        });
        guestContainer.insertBefore(span, guestInput);
    }

    if (guestInput) {
        guestInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                const name = guestInput.value.trim();
                if (name) { addGuestTag(name); guestInput.value = ''; savePresence(); }
            }
        });
    }

    // Suppression invités existants (rendu serveur)
    document.querySelectorAll('.presence-guest-remove').forEach(btn => {
        btn.addEventListener('click', function () {
            btn.closest('.presence-guest-tag').remove();
            savePresence();
        });
    });
})();
