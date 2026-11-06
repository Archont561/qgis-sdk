Feature: Every layer kind a project can hold is a layer the SDK describes
  QGIS holds more than vectors and rasters: a mesh of a hydrodynamic model, a
  point cloud of a survey, a vector tile layer of a basemap, an annotation layer
  a plugin drew and a 3D tiled scene. A plugin that can only see two of them
  cannot list a project honestly, and a page that reads a layer without knowing
  which of the seven it holds draws the wrong row.

  Each kind answers its own description, with the numbers that kind actually
  has - vertices and faces for a mesh, points and attributes for a point cloud,
  zooms and a source type for a vector tile, items for an annotation layer, a
  box for a tiled scene - and never a field borrowed from a kind it is not. A
  layer input, a picker and the wire all name the same seven kinds, so the
  filter a page applies is the filter the host applied.

  These scenarios run on the fake backend: a plugin author's own pure tests
  arrange the same declared layers and read the same descriptions.

  Background:
    Given a runtime that can open every layer kind

  Scenario: A mesh answers its vertices, faces and dataset groups
    When the plugin opens the bundled mesh
    Then the mesh describes 4 vertices, 2 faces and 1 dataset group

  Scenario: A point cloud answers its point count and attributes
    When the plugin opens the bundled point cloud
    Then the point cloud describes 12 points
    And the point cloud lists the attributes "X", "Y", "Z" and "Intensity"

  Scenario: A vector tile layer answers its source type and zooms
    When the plugin opens the bundled vector tiles
    Then the vector tile layer describes an "xyz" source
    And the vector tile layer covers zooms 0 to 14

  Scenario: An annotation layer answers how many items it holds
    When the plugin opens the bundled annotations
    Then the annotation layer describes 3 items

  Scenario: A tiled scene answers where it sits rather than what it holds
    When the plugin opens the bundled tiled scene
    Then the tiled scene describes the box 21.0, 52.0, 21.3, 52.2

  Scenario: Every kind is listed beside the others
    Given the plugin has opened one layer of every kind
    When the layers service lists the project
    Then the kinds read vector, mesh, point_cloud, vector_tile, annotation, tiled_scene and raster

  Scenario: A dataset is opened as the kind it was declared as
    When the plugin opens the mesh as a point cloud
    Then the SDK refuses it as a missing layer

  Scenario: A layer input names the kind its picker offers
    Given a form with a "mesh" layer input and a "tiled_scene" layer input
    When the form fields are described for the wire
    Then the first input offers kind "mesh"
    And the second input offers kind "tiled_scene"

  Scenario: An unknown kind is refused where it is declared
    When a layer input asks for kind "sound"
    Then the declaration is refused naming the seven kinds and "any"
