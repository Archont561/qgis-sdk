import { RootProvider } from "fumadocs-ui/provider/next";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { BASE, DESCRIPTION, REPOSITORY, SITE, TITLE } from "@/site";
import "./global.css";

export const metadata: Metadata = {
	metadataBase: new URL(`${SITE}${BASE}`),
	title: { default: TITLE, template: `%s | ${TITLE}` },
	description: DESCRIPTION,
	applicationName: TITLE,
	authors: [{ name: "Archont561", url: REPOSITORY }],
	keywords: [
		"QGIS",
		"plugin",
		"Python",
		"TypeScript",
		"SDK",
		"QWebEngineView",
		"Processing",
	],
	openGraph: {
		type: "website",
		siteName: TITLE,
		title: TITLE,
		description: DESCRIPTION,
		url: `${SITE}${BASE}/`,
	},
	twitter: {
		card: "summary_large_image",
		title: TITLE,
		description: DESCRIPTION,
	},
	icons: { icon: `${BASE}/favicon.svg` },
	alternates: { canonical: `${BASE}/` },
};

export default function RootLayout({ children }: { children: ReactNode }) {
	return (
		<html lang="en" suppressHydrationWarning>
			<body className="flex min-h-screen flex-col">
				<RootProvider
					search={{
						// The index is exported at build time by
						// `app/api/search/route.ts`; the dialog downloads it and
						// searches in the browser, so the site needs no server.
						options: { type: "static", api: `${BASE}/api/search` },
					}}
				>
					{children}
				</RootProvider>
			</body>
		</html>
	);
}
