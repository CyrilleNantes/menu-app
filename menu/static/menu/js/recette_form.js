/* recette_form.js — formulaire recette dynamique (vanilla JS) */
(function () {
    'use strict';

    // ── Helpers ──────────────────────────────────────────────────────────────

    function updateCount(hiddenId, count) {
        const el = document.getElementById(hiddenId);
        if (el) el.value = count;
    }

    // ── Re-indexation ingrédients d'un groupe ────────────────────────────────

    function reindexIngredients(groupEl, g) {
        const rows = groupEl.querySelectorAll('.ing-row');
        rows.forEach((row, i) => {
            row.dataset.ingIdx = i;
            row.querySelector('.ing-name').name         = `ing_name_${g}_${i}`;
            row.querySelector('.ing-qty').name          = `ing_qty_${g}_${i}`;
            row.querySelector('.ing-qty-note').name     = `ing_qty_note_${g}_${i}`;
            row.querySelector('.ing-unit').name         = `ing_unit_${g}_${i}`;
            row.querySelector('.ing-category').name     = `ing_category_${g}_${i}`;
            const optCb = row.querySelector('input[type=checkbox]');
            if (optCb) optCb.name = `ing_optional_${g}_${i}`;
        });
        const ingCount = groupEl.querySelector('.ing-count');
        if (ingCount) { ingCount.name = `group_ing_count_${g}`; ingCount.value = rows.length; }
        const container = groupEl.querySelector('.ings-container');
        if (container) container.dataset.ingCount = rows.length;
    }

    // ── Re-indexation groupes ────────────────────────────────────────────────

    function reindexGroups() {
        const groups = document.querySelectorAll('#groups-container .group-block');
        groups.forEach((group, g) => {
            group.dataset.groupIdx = g;
            const nameInput = group.querySelector('.group-block__name');
            if (nameInput) nameInput.name = `group_name_${g}`;
            reindexIngredients(group, g);
        });
        updateCount('group_count', groups.length);
    }

    // ── Re-indexation étapes ─────────────────────────────────────────────────

    function reindexSteps() {
        const steps = document.querySelectorAll('#steps-container .step-block');
        steps.forEach((step, s) => {
            step.dataset.stepIdx = s;
            step.querySelector('.step-instruction').name = `step_instruction_${s}`;
            const note = step.querySelector('.step-chef-note');
            if (note) note.name = `step_chef_note_${s}`;
            const timer = step.querySelector('.step-timer');
            if (timer) timer.name = `step_timer_${s}`;
            const num = step.querySelector('.step-block__num');
            if (num) num.textContent = s + 1;
        });
        updateCount('step_count', steps.length);
    }

    // ── Re-indexation sections ───────────────────────────────────────────────

    function reindexSections() {
        const sections = document.querySelectorAll('#sections-container .section-block');
        sections.forEach((sec, s) => {
            sec.dataset.sectionIdx = s;
            sec.querySelector('select').name                  = `section_type_${s}`;
            sec.querySelector('.section-title').name          = `section_title_${s}`;
            sec.querySelector('.section-content').name        = `section_content_${s}`;
        });
        updateCount('section_count', sections.length);
    }

    // ── Créer une ligne ingrédient vierge ────────────────────────────────────

    function createIngRow(g, i) {
        const div = document.createElement('div');
        div.className = 'ing-row';
        div.dataset.ingIdx = i;
        div.innerHTML = `
            <input type="text"   name="ing_name_${g}_${i}"     placeholder="Ingrédient *" class="ing-name">
            <input type="number" name="ing_qty_${g}_${i}"      placeholder="Qté" step="any" class="ing-qty">
            <input type="text"   name="ing_qty_note_${g}_${i}" placeholder="Ex. 150–200g" class="ing-qty-note">
            <input type="text"   name="ing_unit_${g}_${i}"     placeholder="Unité" class="ing-unit">
            <input type="text"   name="ing_category_${g}_${i}" placeholder="Catégorie" class="ing-category">
            <label class="ing-optional-label">
                <input type="checkbox" name="ing_optional_${g}_${i}"> Opt.
            </label>
            <button type="button" class="btn-icon btn-remove-ing" title="Supprimer">✕</button>`;
        return div;
    }

    // ── Créer un bloc groupe vierge ──────────────────────────────────────────

    function createGroupBlock(g) {
        const div = document.createElement('div');
        div.className = 'group-block';
        div.dataset.groupIdx = g;
        div.innerHTML = `
            <div class="group-block__header">
                <input type="text" name="group_name_${g}" placeholder="Nom du groupe (ex. Base viande)" class="group-block__name">
                <button type="button" class="btn-icon btn-remove-group" title="Supprimer ce groupe">✕</button>
            </div>
            <input type="hidden" class="ing-count" name="group_ing_count_${g}" value="0">
            <div class="ings-container" data-ing-count="0"></div>
            <button type="button" class="btn btn--secondary btn--sm btn-add-ing">+ Ingrédient</button>`;
        return div;
    }

    // ── Créer un bloc étape vierge ───────────────────────────────────────────

    function createStepBlock(s) {
        const div = document.createElement('div');
        div.className = 'step-block';
        div.dataset.stepIdx = s;
        div.innerHTML = `
            <div class="step-block__header">
                <span class="step-block__num">${s + 1}</span>
                <button type="button" class="btn-icon btn-remove-step" title="Supprimer">✕</button>
            </div>
            <textarea name="step_instruction_${s}" placeholder="Instruction de l'étape *" rows="3" class="step-instruction"></textarea>
            <input type="text" name="step_chef_note_${s}" placeholder="👉 Note du chef (optionnel)" class="step-chef-note">
            <div class="step-timer-row">
                <label>Timer :</label>
                <input type="number" name="step_timer_${s}" placeholder="secondes" min="0" class="step-timer">
                <span class="form-help">secondes (0 = pas de timer)</span>
            </div>`;
        return div;
    }

    // ── Créer un bloc section vierge ─────────────────────────────────────────

    function createSectionBlock(s) {
        const div = document.createElement('div');
        div.className = 'section-block';
        div.dataset.sectionIdx = s;
        div.innerHTML = `
            <div class="section-block__header">
                <select name="section_type_${s}">
                    <option value="critique">⚠️ Points critiques</option>
                    <option value="conseil">💡 Conseils</option>
                    <option value="difference">🎯 Ce qui fait la différence</option>
                    <option value="libre">Section libre</option>
                </select>
                <button type="button" class="btn-icon btn-remove-section" title="Supprimer">✕</button>
            </div>
            <input type="text"  name="section_title_${s}"   placeholder="Titre (optionnel)" class="section-title">
            <textarea           name="section_content_${s}" rows="4" placeholder="Contenu…" class="section-content"></textarea>`;
        return div;
    }

    // ── Délégation d'événements ──────────────────────────────────────────────

    document.addEventListener('click', function (e) {

        // + Groupe
        if (e.target.id === 'btn-add-group') {
            const container = document.getElementById('groups-container');
            const g = container.querySelectorAll('.group-block').length;
            container.appendChild(createGroupBlock(g));
            updateCount('group_count', g + 1);
        }

        // + Ingrédient dans un groupe
        if (e.target.classList.contains('btn-add-ing')) {
            const groupEl = e.target.closest('.group-block');
            const g = parseInt(groupEl.dataset.groupIdx, 10);
            const container = groupEl.querySelector('.ings-container');
            const i = container.querySelectorAll('.ing-row').length;
            container.appendChild(createIngRow(g, i));
            const ingCount = groupEl.querySelector('.ing-count');
            if (ingCount) ingCount.value = i + 1;
        }

        // ✕ Supprimer un ingrédient
        if (e.target.classList.contains('btn-remove-ing')) {
            const groupEl = e.target.closest('.group-block');
            e.target.closest('.ing-row').remove();
            const g = parseInt(groupEl.dataset.groupIdx, 10);
            reindexIngredients(groupEl, g);
        }

        // ✕ Supprimer un groupe
        if (e.target.classList.contains('btn-remove-group')) {
            e.target.closest('.group-block').remove();
            reindexGroups();
        }

        // + Étape
        if (e.target.id === 'btn-add-step') {
            const container = document.getElementById('steps-container');
            const s = container.querySelectorAll('.step-block').length;
            container.appendChild(createStepBlock(s));
            updateCount('step_count', s + 1);
        }

        // ✕ Supprimer une étape
        if (e.target.classList.contains('btn-remove-step')) {
            e.target.closest('.step-block').remove();
            reindexSteps();
        }

        // + Section
        if (e.target.id === 'btn-add-section') {
            const container = document.getElementById('sections-container');
            const s = container.querySelectorAll('.section-block').length;
            container.appendChild(createSectionBlock(s));
            updateCount('section_count', s + 1);
        }

        // ✕ Supprimer une section
        if (e.target.classList.contains('btn-remove-section')) {
            e.target.closest('.section-block').remove();
            reindexSections();
        }

        // Dialog suppression
        if (e.target.id === 'btn-delete') {
            document.getElementById('dialog-delete')?.showModal();
        }
        if (e.target.id === 'btn-cancel-delete') {
            document.getElementById('dialog-delete')?.close();
        }
    });

})();
