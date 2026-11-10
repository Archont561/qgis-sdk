/**
 * The versions the workspace is at, read from the manifest snapshot the
 * generator writes, so a release page cannot drift from the packages it
 * describes.
 */
import versions from "@/lib/generated/versions.json";

export function Versions() {
	return (
		<span>
			Python <code>qgis-sdk {versions.python}</code>, TypeScript{" "}
			<code>@archont561/qgis-sdk {versions.typescript}</code>, components{" "}
			<code>@archont561/qgis-sdk-ui {versions.ui}</code>
		</span>
	);
}
