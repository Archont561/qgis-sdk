import Link from "next/link";

export default function NotFound() {
	return (
		<main className="mx-auto flex w-full max-w-3xl flex-col items-start gap-4 px-4 py-24">
			<h1 className="font-semibold text-3xl">Page not found</h1>
			<p className="text-fd-muted-foreground">
				The page you asked for is not part of the documentation. The guides are
				the quickest way back.
			</p>
			<Link
				className="rounded-lg bg-fd-primary px-4 py-2 font-medium text-fd-primary-foreground text-sm no-underline"
				href="/"
			>
				Back to the start
			</Link>
		</main>
	);
}
