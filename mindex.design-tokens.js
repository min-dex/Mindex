(function () {
  const TYPOGRAPHY = Object.freeze({
    label: Object.freeze({ size: 12, weight: 700 }),
    meta: Object.freeze({ size: 12, weight: 500 }),
    control: Object.freeze({ size: 14, weight: 600 }),
    cardTitle: Object.freeze({ size: 16, weight: 700 }),
    pageTitle: Object.freeze({ size: 20, weight: 700 }),
  });

  const ICONS = Object.freeze({
    helper: 14,
    normal: 16,
    large: 20,
    stroke: 1.5,
  });

  const TABS = Object.freeze({
    width: 180,
    size: 13,
    weight: 600,
    activeWeight: 700,
  });

  const BUTTONS = Object.freeze({
    topbar: Object.freeze({ size: 40 }),
    icon: Object.freeze({ size: 35 }),
    dense: Object.freeze({ size: 30 }),
    compact: Object.freeze({ size: 28 }),
  });

  const SPACING = Object.freeze({
    denseStep: 5,
    layoutStep: 10,
    detailPadding: 25,
  });

  const MOTION = Object.freeze({
    shell: Object.freeze({
      duration: "120ms",
      easing: "cubic-bezier(.2, 0, .2, 1)",
    }),
  });

  const SERVICE_NAVIGATION = Object.freeze({
    homeWeekTitle: "최근 예배",
    serviceWeekTitle: "최근 예배",
    serviceListTitle: "전체 예배",
    templatesTitle: "템플릿",
  });

  const BUTTON_INTENT = Object.freeze({
    primary: "primary",
    secondary: "secondary",
    iconOnly: "iconOnly",
    danger: "danger",
  });

  window.MINDEX_DESIGN_TOKENS = Object.freeze({
    version: "2026-08-30",
    typography: TYPOGRAPHY,
    icons: ICONS,
    tabs: TABS,
    buttons: BUTTONS,
    motion: MOTION,
    spacing: SPACING,
    serviceNavigation: SERVICE_NAVIGATION,
    buttonIntent: BUTTON_INTENT,
  });
}());
