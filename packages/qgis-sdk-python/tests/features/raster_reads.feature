Feature: A raster is a layer the SDK reads band by band
  A raster is a layer, not a special case: it is opened, it is listed beside the
  vectors and the project holds both, and it is described by its bands - how
  many, which data type, where its no-data value sits and how big a pixel is.
  A point sample answers the value of the cell under it and answers nothing for
  a no-data cell, because "no data" and "all zeros" are different answers and a
  page that drew a zero would draw a valley that is not there.

  These scenarios run on the fake backend, so a plugin author's own pure tests
  and this feature read the same numbers from the same three-by-two grid.

  Background:
    Given a runtime with the raster backend and the three-by-two grid
    And the vector layer "points" is open in the project

  Scenario: An opened grid is described band by band
    When the plugin opens the bundled elevation grid
    Then the raster backend describes one Float64 band
    And the grid's no-data value is -9999.0

  Scenario: A raster is listed beside the vector layers
    When the plugin opens the bundled elevation grid
    Then the layers service lists a vector and a raster, in that order

  Scenario: A point inside a cell answers that cell
    Given the plugin opens the bundled elevation grid
    When the grid is sampled at 21.05 east and 52.15 north
    Then the sample answers 1.0 in band 1
    And the sample reports the raster's own CRS

  Scenario: A no-data cell answers nothing rather than zero
    Given the plugin opens the bundled elevation grid
    When the grid is sampled at 21.15 east and 52.05 north
    Then the sample answers no value

  Scenario: A band's statistics count every cell of the band
    Given the plugin opens the bundled elevation grid
    When band 1 is measured
    Then the statistics report 5 valid cells and 1 no-data cell
    And the statistics report a mean of 3.2

  Scenario: A vector id is not a raster id
    When the vector layer's id is sampled as a raster
    Then the SDK refuses it as a missing raster layer
