/* mode_cuisine.js — Ingrédients cochables, étapes + timers */
(function () {
    'use strict';

    const meta       = document.getElementById('cuisine-meta');
    const STEP_COUNT = meta ? parseInt(meta.dataset.stepCount, 10) : 0;
    const progressEl = document.getElementById('cuisine-progress');

    let currentIndex        = 0;
    let activeTimerInterval = null;

    // ── Ingrédients ────────────────────────────────────────────────────────

    document.querySelectorAll('.cuisine-ing').forEach(el => {
        el.addEventListener('click', () => toggleIng(el));
        el.addEventListener('keydown', e => {
            if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggleIng(el); }
        });
    });

    function toggleIng(el) {
        const checked = el.classList.toggle('cuisine-ing--checked');
        el.setAttribute('aria-checked', String(checked));
        const icon = el.querySelector('.cuisine-ing__icon');
        if (icon) icon.textContent = checked ? '●' : '○';
    }

    // ── Collapse ingrédients ───────────────────────────────────────────────

    const btnIngsToggle  = document.getElementById('btn-ings-toggle');
    const ingsContainer  = document.getElementById('cuisine-ings');
    const ingsArrow      = document.getElementById('ings-arrow');

    btnIngsToggle?.addEventListener('click', () => {
        const expanded = btnIngsToggle.getAttribute('aria-expanded') === 'true';
        btnIngsToggle.setAttribute('aria-expanded', String(!expanded));
        ingsContainer.style.display = expanded ? 'none' : '';
        if (ingsArrow) ingsArrow.textContent = expanded ? '▼' : '▲';
    });

    // ── Étapes ────────────────────────────────────────────────────────────

    const steps = Array.from(document.querySelectorAll('.cuisine-step'));

    function activateStep(index) {
        steps.forEach((s, i) => {
            s.classList.toggle('cuisine-step--active', i === index);
            s.classList.toggle('cuisine-step--done',   i < index);
            s.classList.toggle('cuisine-step--future', i > index);
        });
        if (progressEl) progressEl.textContent = `${index + 1} / ${STEP_COUNT}`;
        if (steps[index]) {
            setTimeout(() => steps[index].scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
        }
    }

    // Init
    if (STEP_COUNT > 0) activateStep(0);

    steps.forEach((step, index) => {
        const validateBtn = step.querySelector('.btn-validate-step');
        const skipBtn     = step.querySelector('.btn-skip-timer');
        const timerSec    = parseInt(step.dataset.timer || '0', 10);

        // ── Bouton principal ──────────────────────────────────────────────
        validateBtn?.addEventListener('click', () => {
            if (step.dataset.timerRunning === 'true') {
                // Timer en cours : on ne fait rien, l'utilisateur doit passer ou attendre
                return;
            }
            if (timerSec > 0 && !step.dataset.timerStarted) {
                // Démarrer le timer
                step.dataset.timerStarted = 'true';
                step.dataset.timerRunning = 'true';
                validateBtn.disabled   = true;
                validateBtn.textContent = '⏱ En cours…';
                if (skipBtn) skipBtn.style.display = '';

                startTimer(step, timerSec, () => {
                    // Timer terminé → activer le bouton "Étape suivante"
                    step.dataset.timerRunning = 'false';
                    validateBtn.disabled   = false;
                    validateBtn.textContent = isLastStep(index) ? '🏁 Terminer la recette' : '→ Étape suivante';
                    validateBtn.classList.add('cuisine-btn--pulse');
                    if (skipBtn) skipBtn.style.display = 'none';
                });
            } else {
                // Pas de timer (ou déjà fait) → avancer
                advance(index);
            }
        });

        // ── Bouton passer le timer ────────────────────────────────────────
        skipBtn?.addEventListener('click', () => {
            if (activeTimerInterval) {
                clearInterval(activeTimerInterval);
                activeTimerInterval = null;
            }
            step.dataset.timerRunning = 'false';
            validateBtn.disabled   = false;
            validateBtn.textContent = isLastStep(index) ? '🏁 Terminer la recette' : '→ Étape suivante';
            validateBtn.classList.add('cuisine-btn--pulse');
            skipBtn.style.display = 'none';

            const display = document.getElementById(`timer-display-${index}`);
            if (display) {
                display.textContent = 'passé';
                display.classList.remove('cuisine-timer--warning');
            }
        });
    });

    function isLastStep(index) {
        return index >= STEP_COUNT - 1;
    }

    function advance(index) {
        if (activeTimerInterval) {
            clearInterval(activeTimerInterval);
            activeTimerInterval = null;
        }
        if (index + 1 < STEP_COUNT) {
            currentIndex = index + 1;
            activateStep(currentIndex);
        } else {
            showDone();
        }
    }

    // ── Timer ──────────────────────────────────────────────────────────────

    function startTimer(step, seconds, onComplete) {
        const display = step.querySelector('.cuisine-timer__display');
        let remaining = seconds;
        renderTime(display, remaining);

        activeTimerInterval = setInterval(() => {
            remaining--;
            renderTime(display, remaining);

            if (remaining <= 30 && display) {
                display.classList.add('cuisine-timer--warning');
            }
            if (remaining <= 0) {
                clearInterval(activeTimerInterval);
                activeTimerInterval = null;
                if (display) {
                    display.textContent = '00:00';
                    display.classList.remove('cuisine-timer--warning');
                    display.classList.add('cuisine-timer--done');
                }
                playAlarm();
                onComplete();
            }
        }, 1000);
    }

    function renderTime(el, seconds) {
        if (!el) return;
        const s = Math.max(0, seconds);
        const m = Math.floor(s / 60);
        const r = s % 60;
        el.textContent = `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
    }

    // ── Alarme sonore (Web Audio API) ─────────────────────────────────────

    function playAlarm() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            [0, 0.4, 0.8].forEach(delay => {
                const osc  = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.type = 'sine';
                osc.frequency.value = 880;
                gain.gain.setValueAtTime(0.55, ctx.currentTime + delay);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 0.5);
                osc.start(ctx.currentTime + delay);
                osc.stop(ctx.currentTime + delay + 0.6);
            });
        } catch (_) { /* Web Audio non disponible */ }
    }

    // ── Fin de recette ────────────────────────────────────────────────────

    function showDone() {
        if (activeTimerInterval) { clearInterval(activeTimerInterval); activeTimerInterval = null; }
        if (progressEl) progressEl.textContent = '✓ Terminé !';
        const doneEl = document.getElementById('cuisine-done');
        if (doneEl) {
            doneEl.style.display = 'block';
            setTimeout(() => doneEl.scrollIntoView({ behavior: 'smooth', block: 'center' }), 80);
        }
    }

    // ── Thème sombre ──────────────────────────────────────────────────────

    const themeBtn = document.getElementById('btn-theme-toggle');
    themeBtn?.addEventListener('click', () => {
        const dark = document.body.classList.toggle('cuisine-dark');
        themeBtn.textContent = dark ? '☀️' : '🌙';
        themeBtn.title = dark ? 'Passer en thème clair' : 'Passer en thème sombre';
        try { localStorage.setItem('cuisine-theme', dark ? 'dark' : 'light'); } catch (_) {}
    });

    // Restaurer le thème mémorisé
    try {
        if (localStorage.getItem('cuisine-theme') === 'dark') {
            document.body.classList.add('cuisine-dark');
            if (themeBtn) { themeBtn.textContent = '☀️'; themeBtn.title = 'Passer en thème clair'; }
        }
    } catch (_) {}

})();
