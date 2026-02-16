/**
 * Bench HMI — Touch Gesture Handling (T-609)
 * Swipe detection for tab navigation, pull-to-refresh, touch feedback.
 */
(function() {
    'use strict';

    const SWIPE_THRESHOLD = 80;     // px
    const SWIPE_MAX_TIME = 500;     // ms
    const SWIPE_MAX_VERTICAL = 60;  // px — reject diagonal swipes

    let touchStartX = 0;
    let touchStartY = 0;
    let touchStartTime = 0;

    // Tab order for swipe navigation
    const tabOrder = [
        '/bench/',              // Dashboard
        '/bench/test-control/', // Test Control
        '/bench/system/',       // System
        '/bench/settings/',     // Settings
    ];

    function getCurrentTabIndex() {
        const path = window.location.pathname;
        for (let i = 0; i < tabOrder.length; i++) {
            if (path === tabOrder[i]) return i;
        }
        return -1;
    }

    function navigateToTab(index) {
        if (index >= 0 && index < tabOrder.length) {
            window.location.href = tabOrder[index];
        }
    }

    // --- Swipe Detection ---

    document.addEventListener('touchstart', function(e) {
        // Don't intercept scrollable containers or keypad
        if (e.target.closest('.scroll-snap-container, .dut-keypad, .dut-key, input, textarea, select')) return;
        if (e.touches.length !== 1) return;

        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchStartTime = Date.now();
    }, { passive: true });

    document.addEventListener('touchend', function(e) {
        if (!touchStartTime) return;

        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        const dt = Date.now() - touchStartTime;

        touchStartTime = 0;

        // Validate swipe
        if (dt > SWIPE_MAX_TIME) return;
        if (Math.abs(dy) > SWIPE_MAX_VERTICAL) return;
        if (Math.abs(dx) < SWIPE_THRESHOLD) return;

        const currentIdx = getCurrentTabIndex();
        if (currentIdx < 0) return;

        if (dx < 0) {
            // Swipe left → next tab
            navigateToTab(currentIdx + 1);
        } else {
            // Swipe right → previous tab
            navigateToTab(currentIdx - 1);
        }
    }, { passive: true });

    // --- Touch Active Feedback ---

    document.addEventListener('touchstart', function(e) {
        const btn = e.target.closest('.btn-hmi, .wizard-meter-card, .wizard-mode-card, .history-card');
        if (btn) btn.classList.add('touch-active');
    }, { passive: true });

    document.addEventListener('touchend', function() {
        document.querySelectorAll('.touch-active').forEach(function(el) {
            el.classList.remove('touch-active');
        });
    }, { passive: true });

    document.addEventListener('touchcancel', function() {
        document.querySelectorAll('.touch-active').forEach(function(el) {
            el.classList.remove('touch-active');
        });
    }, { passive: true });

})();
