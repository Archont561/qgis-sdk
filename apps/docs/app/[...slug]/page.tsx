import defaultMdxComponents from "fumadocs-ui/mdx";
import {
	DocsBody,
	DocsDescription,
	DocsPage,
	DocsTitle,
} from "fumadocs-ui/page";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CliWalkthrough } from "@/components/cli-walkthrough";
import { CompatNotice } from "@/components/compat-notice";
import { RegistryStats } from "@/components/registry-stats";
import { Versions } from "@/components/versions";
import edits from "@/lib/generated/pages.json";
import { source } from "@/lib/source";
import { REPOSITORY } from "@/site";

/** `https://github.com/Archont561/qgis-sdk` -> the two parts a link needs. */
const [, OWNER, REPO] = /github\.com\/([^/]+)\/([^/]+)/.exec(REPOSITORY) ?? [];

interface Props {
	params: Promise<{ slug: string[] }>;
}

export default async function Page({ params }: Props) {
	const { slug } = await params;
	const page = source.getPage(slug);
	if (page === undefined) {
		notFound();
	}
	const edit = (
		edits as Record<string, { edit: string; lastUpdated?: string }>
	)[page.url];
	const MDX = page.data.body;
	return (
		<DocsPage
			toc={page.data.toc}
			full={page.data.full}
			tableOfContent={{ style: "clerk" }}
			lastUpdate={edit?.lastUpdated}
			editOnGithub={
				edit && OWNER && REPO
					? { owner: OWNER, repo: REPO, path: edit.edit }
					: undefined
			}
		>
			<DocsTitle>{page.data.title}</DocsTitle>
			<DocsDescription>{page.data.description}</DocsDescription>
			<DocsBody>
				<MDX
					components={{
						...defaultMdxComponents,
						CliWalkthrough,
						CompatNotice,
						RegistryStats,
						Versions,
					}}
				/>
			</DocsBody>
		</DocsPage>
	);
}

export function generateStaticParams(): { slug: string[] }[] {
	return source.generateParams();
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
	const { slug } = await params;
	const page = source.getPage(slug);
	if (page === undefined) {
		return {};
	}
	return {
		title: page.data.title,
		description: page.data.description,
		alternates: { canonical: `${page.url}/` },
	};
}
