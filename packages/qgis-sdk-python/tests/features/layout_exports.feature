Feature: A print layout becomes a file, and an atlas becomes one file per feature
  A plugin lists the print layouts the project holds, loads a template into it,
  exports a layout to PDF, PNG or SVG, and runs an atlas over a coverage layer.
  An export is a job: the body runs on a worker, the host shows it as a task,
  progress moves and the cancel button asks the render to stop. A blocking form
  of the same work exists for a caller that has to answer inside one request -
  the bridge, a script, a test - and answers the very same file.

  Two shapes are deliberate here. A destination is a ref the host minted, never
  a path a caller typed, so the export lands where the host said and nowhere
  else. And one image holds one page, so a PNG of a two-page layout is refused
  rather than answered with a file name that quietly means the first page.

  These scenarios run on the fake backend, so a plugin author's pure tests and
  this feature read the same layout names, the same page counts and the same
  coverage ids.

  Background:
    Given a runtime with the layout backend and a one-page layout "cover"
    And the project holds a two-page layout "report"
    And the project holds an atlas "atlas" over the three reference points

  Scenario: The project describes the layouts it holds
    When the plugin lists the print layouts
    Then the project reports "report" with 2 pages and no atlas
    And the project reports "atlas" with a coverage layer

  Scenario: A PDF export runs as a job and holds every page
    When the plugin exports "report" as a PDF
    Then the export has not started
    When the job is driven to its end
    Then the job succeeded with a PDF of 2 pages
    And the exported file is inside the host's output directory

  Scenario: An export reports progress
    When the plugin exports "report" as a PDF and watches its progress
    And the job is driven to its end
    Then the progress ends at 1.0 and never went backwards

  Scenario: A cancelled export writes nothing
    Given the plugin exports "report" as a PDF
    When the export is cancelled before its body runs
    And the job is driven to its end
    Then the job is cancelled and no PDF was written

  Scenario: An image holds one page
    When the plugin exports "cover" as a PNG
    And the job is driven to its end
    Then the export is a PNG of 1 page
    When the plugin exports "report" as a PNG
    Then the SDK refuses the destination as holding more than one page

  Scenario: A destination is a ref the host minted
    When the plugin exports "report" to a path it typed
    Then the SDK refuses the destination as not a ref
    When the plugin exports "report" to a ref the host minted
    Then the export landed where the ref named

  Scenario: An existing file is only replaced on request
    Given "report" was exported to a ref the host minted
    When the same ref is exported to again
    Then the SDK refuses the destination as existing
    When the same ref is exported to with overwrite
    Then the export replaced the file

  Scenario: An atlas writes one file per coverage feature
    When the atlas "atlas" is run with the pattern "sheet-{index:02d}-{feature_id}"
    Then the atlas wrote 3 files, one for each feature
    And the file names are the ones the pattern asks for

  Scenario: An atlas pattern may only name what a page knows
    When the atlas "atlas" is run with the pattern "{page}.{feature_id}"
    Then the SDK refuses the pattern's unknown field "page"

  Scenario: A layout with no atlas cannot run one
    When the atlas "report" is run
    Then the SDK refuses the atlas as missing

  Scenario: A template adds a layout named after its file
    When the plugin loads the template "templated.qpt"
    Then the project reports "templated" with 1 page and no atlas

  Scenario: A template is a ref, not a path
    When the plugin loads the template as a path it typed
    Then the SDK refuses the template as not a ref
