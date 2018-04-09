<?php

namespace Drupal\avoindata_frontpage\Plugin\Block;

use Drupal\Core\Block\BlockBase;

/**
 * Provides a block showcasing a key figure and label.
 * For example: "99" "problems".
 *
 * @Block(
 *   id = "key_figure",
 *   admin_label = @Translation("Key figure"),
 *   category = @Translation("CKAN API"),
 * )
 */
class KeyFigure extends BlockBase {

  /**
   * {@inheritdoc}
   */
  public function build() {
    return array(
      '#markup' => '99 problems',
    );
  }

}