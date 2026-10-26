<script>
// A component that runs the driver's setup during initialisation, so the
// adapter's `onDestroy` has a component to attach to; unmounting it is
// the teardown the behaviour suite calls `dispose`.
let { setup } = $props();
setup();
</script>
