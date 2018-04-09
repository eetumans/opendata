<?php

namespace Drupal\avoindata_frontpage\Plugin\Block;

use Drupal\Core\Block\BlockBase;

/**
 * Provides a search field for CKAN searches.
 *
 * @Block(
 *   id = "search_ckan",
 *   admin_label = @Translation("Search CKAN"),
 *   category = @Translation("Search"),
 * )
 */
class SearchCKAN extends BlockBase {

  /**
   * {@inheritdoc}
   */
  public function build() {
    return array(
      '#markup' => 'Hakupalkki',
    );
  }

}