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
 * exists so the hand-written entry point stays reviewable.
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
	type IdPage,
	type LayerPage,
	type LayerRequest,
	type NotificationsInfoRequest,
	type PageRequest,
	type SettingsGetRequest,
	type StylesApplyRequest,
	type VectorLayerInfo,
} from "./generated/host";
