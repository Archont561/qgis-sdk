Feature: A layer's appearance is data, not a live QGIS object
  Symbology is how a layer is drawn: a renderer that decides which symbol a
  feature gets, the symbols themselves, and the labelling that writes a field
  over the map. A plugin that can only apply a packaged style can dress a layer
  the way the catalog says and nothing else; a page that wants to colour by an
  attribute has to reach into QGIS directly, which is what this SDK exists to
  avoid.

  What crosses the boundary is a description. A renderer is one of four kinds -
  single symbol, categorized, graduated, rule-based - each with the fields that
  kind actually has, and a symbol is a marker, a line or a fill with a colour, a
  size and an outline. Set one and get the same one back; export a style as QML
  or SLD text and import it into another layer. The style manager is readable
  for the same reason: a page that offers "the symbols this QGIS ships" needs to
  know what they are called.

  This is a curated surface, not a copy of the renderer API (decision-16): a
  renderer this SDK does not model is refused by name rather than half
  described, and an expression a rule cannot parse is QGIS's to refuse, not
  ours to guess.

  These scenarios run on the fake backend: a plugin author's own pure tests
  arrange the same layers and read the same descriptions.

  Background:
    Given a runtime with symbology, labelling and a style manager

  Scenario: A freshly opened layer answers a single symbol renderer
    When the plugin opens the reference points
    Then the layer is drawn by a single symbol renderer
    And its symbol is a marker

  Scenario: A categorized renderer round-trips through set and get
    When the plugin draws the points by category of "kind"
    Then the layer is drawn by a categorized renderer on "kind"
    And it lists 2 categories, the first for value "a" in "#ff0000"

  Scenario: A graduated renderer keeps its classification mode
    When the plugin draws the points by graduated "value" in four classes
    Then the layer is drawn by a graduated renderer on "value"
    And it lists 4 classes between 0.0 and 4.0
    And the renderer classifies by "quantile"

  Scenario: A rule-based renderer keeps its filters
    When the plugin draws the points by two rules
    Then the layer is drawn by a rule-based renderer
    And its rules filter on "value > 2" and "value <= 2"

  Scenario: A renderer names its kind on the wire
    When each renderer is described for the wire
    Then the wire kinds read single_symbol, categorized, graduated and rule_based

  Scenario: An unmodelled renderer is refused by name
    When the plugin asks for a symbology this SDK does not model
    Then it is refused naming the four renderer kinds

  Scenario: A symbol keeps its colour, size and outline
    When the plugin draws the points with a 3.5 mm red marker outlined in blue
    Then the symbol answers "#ff0000", 3.5 and an outline in "#0000ff"

  Scenario: Labelling switches on with a field
    When the plugin labels the points by "name"
    Then the layer's labelling is on, on "name", at 10 points

  Scenario: Labelling switches off again
    Given the points are labelled by "name"
    When the plugin switches labelling off
    Then the layer's labelling is off

  Scenario: Labels without a field are refused where they are declared
    When a labelling is declared on with no field
    Then the declaration is refused naming the field it needs

  Scenario: A style exports to text and imports back into the same layer
    When the plugin exports the layer's style as QML
    And the plugin imports that text back
    Then the layer keeps its renderer

  Scenario: The style manager lists what it offers
    When the plugin reads the style manager
    Then it lists a symbol, a colour ramp and a label setting

  Scenario: A mesh is not something a renderer can be set on
    When the plugin asks a mesh for its symbology
    Then the SDK refuses it as a mesh
