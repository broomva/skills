// Maestro · design-system bridge.
// The compiled bundle (../../_ds_bundle.js) carries the standard components;
// this adapter exposes them as Ds* globals so app files compose them instead
// of re-implementing. Add new standard components here, never ad-hoc copies.
(() => {
  const DS = window.BroomvaDesignSystem_5727d9;
  if (!DS) {
    console.error("ds-adapter: design-system bundle not loaded · check the _ds_bundle.js path in index.html");
    return;
  }
  window.DS = DS;
  Object.assign(window, {
    DsButton: DS.Button,
    DsIconButton: DS.IconButton,
    DsInput: DS.Input,
    DsCard: DS.Card,
    DsAvatar: DS.Avatar,
    DsStatusBadge: DS.StatusBadge,
    DsComposer: DS.Composer,
    // forms
    DsSelect: DS.Select,
    DsCheckbox: DS.Checkbox,
    DsRadio: DS.Radio,
    DsSwitch: DS.Switch,
    DsTextarea: DS.Textarea,
    DsField: DS.Field,
    // navigation
    DsTabs: DS.Tabs,
    DsSegmented: DS.Segmented,
    DsCommandPalette: DS.CommandPalette,
    // overlays
    DsDialog: DS.Dialog,
    DsConfirmDialog: DS.ConfirmDialog,
    DsMenu: DS.Menu,
    DsMenuItem: DS.MenuItem,
    DsMenuDivider: DS.MenuDivider,
    DsTooltip: DS.Tooltip,
    DsToast: DS.Toast,
    // work primitives
    DsWorkState: DS.WorkState,
    DsLifecycleRail: DS.LifecycleRail,
    DsReceipt: DS.Receipt,
    DsReceiptRow: DS.ReceiptRow,
    DsUndertow: DS.Undertow,
    DsRunCard: DS.RunCard,
    DsAutonomyScoreboard: DS.AutonomyScoreboard,
  });
})();
