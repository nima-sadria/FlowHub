# FAQ

## Where is FlowHub installed?

`/opt/FlowHub`.

## Where do I configure WooCommerce and Nextcloud?

Settings.

## Does setup configure connectors?

No. Setup contains Welcome, Server Profile, Database, Owner Account, and Finish.

## Are writes enabled?

Manual WooCommerce price writes are available only through the protected
Workspace flow: Preview, row selection, Dry Run, Approval, Manual Execute,
read-back verification, and audit. Simple products and variations are
supported. SnappShop and TapsiShop price writes are available only through the
protected Products multi-channel editor with no-write Dry Run, Approval, and
explicit Apply. Marketplace order synchronization runs in a separate worker.
Stock writes, spreadsheet/source writes, automatic pricing, and automatic Apply
remain disabled.

## What is `/opt/flowhub`?

Legacy Compatibility path for older installations. New installations use
`/opt/FlowHub`.
