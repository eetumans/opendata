<?php

namespace Drupal\avoindata_frontpage\Plugin\Block;

use Drupal\Core\Block\BlockBase;
use Drupal\Core\Block\BlockPluginInterface;
use Drupal\Core\Form\FormStateInterface;

/**
 * Provides a text block with title, subtitle, content and link.
 * Editable by admin.
 *
 * @Block(
 *   id = "front_page_introduction",
 *   admin_label = @Translation("Front Page Introduction"),
 *   category = @Translation("Text Block"),
 * )
 */
class FrontPageIntroduction extends BlockBase implements BlockPluginInterface {

  /**
   * {@inheritdoc}
   */
  public function build() {
    $config = $this->getConfiguration();

    $title = !empty($config['title']) ? $config['title'] : "";
    $subtitle = !empty($config['subtitle']) ? $config['subtitle'] : "";
    $introduction = !empty($config['introduction']) ? $config['introduction'] : "";
    $link_url = !empty($config['link_url']) ? $config['link_url'] : "";
    $link_text = !empty($config['link_text']) ? $config['link_text'] : "";

    return array(
      '#markup' => $this->t('Otsikko on @title, alaotsikko on @subtitle!', array(
        '@title' => $title,
        '@subtitle' => $subtitle,
      )),
    );
  }

  /**
   * {@inheritdoc}
   */
  public function blockForm($form, FormStateInterface $form_state) {
    $form = parent::blockForm($form, $form_state);

    $config = $this->getConfiguration();

    $form['title'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Site title'),
      '#description' => $this->t('Shown on front page'),
      '#default_value' => isset($config['title']) ? $config['title'] : '',
    ];

    $form['subtitle'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Subtitle'),
      '#description' => $this->t('Short tag that is shown with title. Used to differentiate beta/dev sites.'),
      '#default_value' => isset($config['subtitle']) ? $config['subtitle'] : '',
    ];

    $form['introduction'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Introduction'),
      '#description' => $this->t('Short introductory text for front page.'),
      '#default_value' => isset($config['introduction']) ? $config['introduction'] : '',
    ];

    $form['link_url'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Link url'),
      '#description' => $this->t('Url of link shown with introductory text.'),
      '#default_value' => isset($config['link_url']) ? $config['link_url'] : '',
    ];

    $form['link_text'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Link text'),
      '#description' => $this->t('Text of link shown with introductory text.'),
      '#default_value' => isset($config['link_text']) ? $config['link_text'] : '',
    ];

    return $form;
  }

  /**
   * {@inheritdoc}
   */
  public function blockSubmit($form, FormStateInterface $form_state) {
    parent::blockSubmit($form, $form_state);
    $values = $form_state->getValues();
    $this->configuration['title'] = $values['title'];
    $this->configuration['subtitle'] = $values['subtitle'];
    $this->configuration['introduction'] = $values['introduction'];
    $this->configuration['link_url'] = $values['link_url'];
    $this->configuration['link_text'] = $values['link_text'];
  }

  /**
   * {@inheritdoc}
   */
  public function defaultConfiguration() {
    return array(
      'title' => 'Avoindata.fi',
      'subtitle' => 'DEV',
      'introduction' => 'Demoversio avoimen datan tieto- ja jakelukanavasta suomalaisille yhteisöille, yrityksille ja kansalaisille.',
      'link_url' => 'https://jotain',
      'link_text' => 'Lue lisää >>',
    );
  }

}