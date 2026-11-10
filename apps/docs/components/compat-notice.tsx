/**
 * The one sentence a reader needs before installing anything: which QGIS and
 * which Python this works on.
 *
 * Both numbers are read from the support matrix at build time (`compat.json`),
 * so the notice moves when a qualification row does - a page cannot promise a
 * version the matrix has not demonstrated.
 */
import Link from "next/link";
import compat from "@/lib/generated/compat.json";

function series(values: readonly { series: string; lts: boolean }[]): string {
	if (values.length === 0) {
		return "no qualified QGIS";
	}
	const named = values.map((value) =>
		value.lts ? `${value.series} LTS` : value.series,
	);
	return named.length === 1
		? named[0]
		: `${named.slice(0, -1).join(", ")} or ${named.at(-1)}`;
}

export function CompatNotice() {
	const { python } = compat;
	const range =
		python.min === python.max ? python.min : `${python.min} to ${python.max}`;
	return (
		<p className="compat-notice mx-auto max-w-3xl text-fd-muted-foreground text-sm">
			<strong className="text-fd-foreground">
				Works on QGIS {series(compat.qgis)}
			</strong>{" "}
			with <strong className="text-fd-foreground">Python {range}</strong>, and
			nothing else is tested -{" "}
			<Link href="/python/supported-targets/" className="underline">
				the support matrix
			</Link>{" "}
			names each qualified row and its evidence.
		</p>
	);
}
