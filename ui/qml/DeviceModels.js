.pragma library

// Hotspot order is computed to guarantee ZERO line crossings
// between dots and right-side callout labels.

var models = {
    "mx_master_3s": {
        image: "MX Master 3-3S.png",
        hotspots: [
            { buttonKey: "mode_shift",   normX: 0.4305, normY: 0.2889, label: "Spin Mode",        placeholder: false },
            { buttonKey: "scroll_down",  normX: 0.3210, normY: 0.3873, label: "Scroll Down",      placeholder: false },
            { buttonKey: "thumb_wheel",  normX: 0.6458, normY: 0.4092, label: "Thumb Wheel",      placeholder: false },
            { buttonKey: "xbutton1",     normX: 0.7101, normY: 0.4418, label: "Back Button",      placeholder: false },
            { buttonKey: "middle",       normX: 0.2590, normY: 0.4197, label: "Middle Button",    placeholder: false },
            { buttonKey: "xbutton2",     normX: 0.6214, normY: 0.5118, label: "Forward Button",   placeholder: false },
            { buttonKey: "scroll_up",    normX: 0.2211, normY: 0.4736, label: "Scroll Up",        placeholder: false },
            { buttonKey: "gesture",      normX: 0.7715, normY: 0.6533, label: "Gesture Button",   placeholder: false },
            { buttonKey: "right_click",  normX: 0.1280, normY: 0.4781, label: "Right Click",      placeholder: false },
            { buttonKey: "left_click",   normX: 0.2137, normY: 0.6095, label: "Left Click",       placeholder: false }
        ]
    },
    "mx_master_4": {
        image: "MX Master 4.png",
        hotspots: [
            { buttonKey: "mode_shift",   normX: 0.3954, normY: 0.3084, label: "Spin Mode",        placeholder: false },
            { buttonKey: "scroll_down",  normX: 0.2863, normY: 0.4267, label: "Scroll Down",      placeholder: false },
            { buttonKey: "thumb_wheel",  normX: 0.6031, normY: 0.3908, label: "Thumb Wheel",      placeholder: false },
            { buttonKey: "xbutton1",     normX: 0.6763, normY: 0.4183, label: "Back Button",      placeholder: false },
            { buttonKey: "xbutton2",     normX: 0.6078, normY: 0.4865, label: "Forward Button",   placeholder: false },
            { buttonKey: "middle",       normX: 0.2191, normY: 0.4649, label: "Middle Button",    placeholder: false },
            { buttonKey: "haptic_panel", normX: 0.6160, normY: 0.5855, label: "Haptic Sense Panel", placeholder: true },
            { buttonKey: "gesture",      normX: 0.5206, normY: 0.5679, label: "Gesture Button",   placeholder: false },
            { buttonKey: "scroll_up",    normX: 0.1817, normY: 0.5328, label: "Scroll Up",        placeholder: false },
            { buttonKey: "right_click",  normX: 0.0851, normY: 0.5807, label: "Right Click",      placeholder: false },
            { buttonKey: "left_click",   normX: 0.1532, normY: 0.7027, label: "Left Click",       placeholder: false }
        ]
    }
}

function get(modelId) {
    if (!modelId || !models[modelId]) return null
    return models[modelId]
}
