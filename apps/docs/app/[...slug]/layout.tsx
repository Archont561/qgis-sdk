import { DocsLayout } from "fumadocs-ui/layouts/docs";
import type { ReactNode } from "react";
import { navLinks } from "@/lib/nav";
import { source } from "@/lib/source";
import { REPOSITORY, TITLE } from "@/site";

/** Every route the content collection owns is rendered inside this layout. */
export default function Layout({ children }: { children: ReactNode }) {
	return (
		<DocsLayout
			tree={source.getPageTree()}
			githubUrl={REPOSITORY}
			links={navLinks}
			nav={{ title: TITLE, url: "/" }}
			tabMode="auto"
			sidebar={{ defaultOpenLevel: 1 }}
		>
			{children}
		</DocsLayout>
	);
}
