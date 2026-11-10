import { Card, Cards } from "fumadocs-ui/components/card";
import { Step, Steps } from "fumadocs-ui/components/steps";
import { HomeLayout } from "fumadocs-ui/layouts/home";
import type { Metadata } from "next";
import { CompatNotice } from "@/components/compat-notice";
import versions from "@/lib/generated/versions.json";
import { hasStorybook, navLinks } from "@/lib/nav";
import { BASE, DESCRIPTION, REPOSITORY, SITE, TITLE } from "@/site";

export const metadata: Metadata = {
	description: DESCRIPTION,
	alternates: { canonical: `${BASE}/` },
};

const jsonLd = {
	"@context": "https://schema.org",
	"@type": "SoftwareApplication",
	name: TITLE,
	description: DESCRIPTION,
	applicationCategory: "DeveloperApplication",
	operatingSystem: "Linux, macOS, Windows",
	offers: { "@type": "Offer", price: "0" },
	url: `${SITE}${BASE}/`,
	downloadUrl: "https://pypi.org/project/qgis-sdk/",
	softwareVersion: versions.python,
	codeRepository: REPOSITORY,
	license: `${REPOSITORY}/blob/main/LICENSE`,
};

export default function Home() {
	return (
		<HomeLayout
			nav={{ title: TITLE, url: "/" }}
			links={navLinks}
			githubUrl={REPOSITORY}
			className="pt-0"
		>
			{/* Search engines show the landing page as a rich result. */}
			<script
				type="application/ld+json"
				// biome-ignore lint/security/noDangerouslySetInnerHtml: build-time constant
				dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
			/>

			<section className="landing-hero mx-auto w-full max-w-5xl px-4 pt-16 pb-8 text-center">
				<h1 className="font-semibold text-4xl tracking-tight sm:text-5xl">
					A Python-first foundation for{" "}
					<span className="grad">QGIS plugins</span>
				</h1>
				<p className="mx-auto mt-5 max-w-3xl text-fd-muted-foreground text-lg leading-relaxed">
					Declare a QGIS plugin as plain Python classes. The SDK derives the
					metadata, the native windows, the Processing algorithms and the typed
					web bridge from those declarations. The pure layers import without
					QGIS, so a plugin is tested from source.
				</p>
				<div className="mt-8 flex flex-wrap items-center justify-center gap-3">
					<a
						className="rounded-lg bg-fd-primary px-5 py-2.5 font-medium text-fd-primary-foreground text-sm no-underline transition hover:opacity-90"
						href={`${BASE}/start/installation/`}
					>
						Get started
					</a>
					<a
						className="rounded-lg border border-fd-border px-5 py-2.5 font-medium text-sm no-underline transition hover:bg-fd-accent"
						href={`${BASE}/python/`}
					>
						Python package guide
					</a>
					<a
						className="rounded-lg px-5 py-2.5 font-medium text-fd-muted-foreground text-sm no-underline transition hover:text-fd-foreground"
						href={REPOSITORY}
					>
						GitHub
					</a>
				</div>

				<code className="install-chip">pip install qgis-sdk</code>

				<div className="mt-6">
					<CompatNotice />
				</div>

				<ul className="versions">
					<li>
						Python kit <code>{versions.python}</code>
					</li>
					<li>
						TypeScript SDK <code>{versions.typescript}</code>
					</li>
					<li>
						Web components <code>{versions.ui}</code>
					</li>
					<li>
						experimental <code>0.x</code> · MIT
					</li>
				</ul>
			</section>

			<div className="prose mx-auto w-full max-w-5xl px-4 pb-16">
				<Cards>
					<Card
						title="One declaration, every host"
						description={
							<>
								<code>QgisSdkPlugin</code>, its actions and a{" "}
								<code>Dialog</code> or <code>Dock</code> built from the UI
								catalogue describe the plugin once. QGIS gets{" "}
								<code>metadata.txt</code> and a <code>classFactory</code> from{" "}
								<code>build</code>; a web page gets a typed <code>QgisSdk</code>{" "}
								from the same declarations.
							</>
						}
					/>
					<Card
						title="Testable without QGIS"
						description={
							<>
								The declarations, the contract layer and the UI catalogue are
								standard library only. <code>qgis-sdk test</code> runs a project
								on the SDK fakes; <code>--target qgis</code> and{" "}
								<code>--target desktop</code> add the native layers when a QGIS
								is there.
							</>
						}
					/>
					<Card
						title="Processing, layers, files, jobs"
						description={
							<>
								<code>ctx</code> reaches layers, the Processing registry (any
								provider, typed parameters), files the user granted, settings,
								the network, the log and scoped background jobs - each service
								with a fake for tests.
							</>
						}
					/>
					<Card
						title="Web views as first-class surfaces"
						description={
							<>
								A <code>QWebEngineView</code> page talks to the plugin over an
								allowlisted bridge:{" "}
								<code>QgisSdk.fromBridgeSchema(schema)</code>, framework-free
								stores, React, Vue and Svelte bindings, and{" "}
								<code>qgis-sdk-ui</code> light-DOM components.
							</>
						}
					/>
				</Cards>

				<h2>From an empty directory to an installable ZIP</h2>
				<Steps>
					<Step>
						<strong>Install</strong> the developer kit:{" "}
						<code>pip install qgis-sdk</code> brings the runtime a plugin
						imports and the <code>qgis-sdk</code> command.
					</Step>
					<Step>
						<strong>Scaffold and check</strong>:{" "}
						<code>qgis-sdk new my_tools --title "My Tools"</code>, then{" "}
						<code>qgis-sdk check</code> - pyproject, syntax, imports, UI rules,
						runtime version.
					</Step>
					<Step>
						<strong>Test and run</strong>: <code>qgis-sdk test</code> without
						QGIS, <code>qgis-sdk dev</code> inside a real QGIS Desktop with
						reload on save.
					</Step>
					<Step>
						<strong>Build</strong>: <code>qgis-sdk build</code> writes{" "}
						<code>dist/&lt;plugin&gt;-&lt;version&gt;.zip</code> with the
						runtime vendored inside - nothing to install on the user's QGIS.
					</Step>
				</Steps>

				{hasStorybook && (
					<section aria-labelledby="demo-title" className="demo">
						<h2 id="demo-title">Try the web components</h2>
						<p>
							This interactive form runs against a scripted host, not a live
							QGIS session. Try the controls or explore the component stories.
						</p>
						<iframe
							title="Interactive buffer form using a scripted host"
							src={`${BASE}/storybook/iframe.html?id=form--buffer&viewMode=story`}
							loading="lazy"
						/>
						<p>
							<a href={`${BASE}/storybook/?path=/story/form--buffer`}>
								Open the component Storybook
							</a>
						</p>
					</section>
				)}

				<h2>Guides</h2>
				<Cards>
					<Card
						title="Test and run a plugin"
						description="Check a project on fakes, then qualify it on a QGIS host."
						href="/guides/test-a-plugin/"
					/>
					<Card
						title="Add a web UI"
						description="Scaffold a web-backed plugin, test both sides and run it in QGIS."
						href="/guides/web-plugin/"
					/>
					<Card
						title="CLI MCP server"
						description="Run developer commands from a trusted MCP client."
						href="/guides/cli-mcp/"
					/>
					<Card
						title="Experimental plugin HTTP API"
						description="Call opted-in plugin actions and streams from outside QGIS."
						href="/guides/experimental-plugin-http/"
					/>
				</Cards>

				<h2>Read the reference</h2>
				<Cards>
					<Card
						title="Python package guide"
						description="Declarations, the UI catalogue, services, Processing, the bridge host side, the scaffold and the command, migration notes."
						href="/python/"
					/>
					<Card
						title="TypeScript SDK guide"
						description="QgisSdk over the generated schema, host namespaces, stores, React, Vue and Svelte bindings, the web components, testing."
						href="/typescript/"
					/>
					<Card
						title="Workspace, harnesses, and evidence"
						description="For contributors: environments, the Pixi and Bun tasks, test layers, the headless and Desktop harnesses and every release gate's evidence."
						href="/contributing/workspace/"
					/>
					<Card
						title="Design decisions"
						description="Every architecture decision behind the SDK in one table - what was decided, its status, and the full record."
						href="/reference/design-decisions/"
					/>
				</Cards>
			</div>
		</HomeLayout>
	);
}
