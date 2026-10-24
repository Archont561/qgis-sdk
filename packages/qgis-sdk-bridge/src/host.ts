/**
 * The curated host surface, generated from `qgis_sdk.bridge.host`.
 *
 * Decision-27: a page reaches the five curated Protocols in `qgis_sdk.services`
 * through this module, and through nothing else of the QGIS API. The manifest it
 * is generated from carries a grant and a thread affinity per operation, and the
 * Python host answers exactly these ids via `register_host_operations`.
 *
 * `generated/host.ts` is generated, never edited: `qgis-sdk bridge generate
 * --host` writes it and CI fails when the checked-in copy differs. This file
 * exists so the hand-written entry point stays reviewable - and it re-exports
 * the runtime validators too, not just their interfaces, because a page that can
 * only assert a type at compile time has nothing to check a reply with.
 */

export {
	createHost,
	HOST_FINGERPRINT,
	HOST_ID,
	HOST_OPERATIONS,
	HOST_SCHEMA_VERSION,
	type HostClientLike,
	HostContractError,
	type HostInvokeOptions,
	type HostOperationId,
	type HostOperations,
	IdPage,
	LayerPage,
	LayerRequest,
	NotificationsInfoRequest,
	PageRequest,
	SettingsGetRequest,
	StylesApplyRequest,
	VectorLayerInfo,
} from "./generated/host";
