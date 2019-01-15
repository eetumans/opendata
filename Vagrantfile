# -*- mode: ruby -*-
# vi: set ft=ruby :
#
# This Vagrantfile sets up virtual machines and installs the opendata service
# on those to create a local development environment.
#
# Tested with Vagrant 2.2.3 and VirtualBox 6.0.0 on Ubuntu 16.04 64-bit

VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  config.vm.define "batch" do |batch|
    batch.vm.box = "bento/ubuntu-16.04"

    batch.vm.network :private_network, ip: "10.10.10.20"

    # Sync source code directories from host to guest
    case RUBY_PLATFORM
    when /mswin|msys|mingw|cygwin|bccwin|wince|emc/
        # Fix Windows file rights, otherwise Ansible tries to execute files
        web1.vm.synced_folder ".", "/vagrant", type:"virtualbox", :mount_options => ["dmode=755","fmode=644"]
    end

    batch.vm.provision "ansible_local" do |ansible|
      ansible.playbook = "ansible/vagrant-multi-server.yml"
      ansible.verbose = "v"
      ansible.inventory_path = "ansible/inventories/vagrant-multi/vagrant"
      ansible.skip_tags = "non-local"
      ansible.limit = 'batch-servers'
      # ansible.extra_vars = { clear_module_cache: true }
      # ansible.tags = "modules,ckan,drupal"
      # ansible.start_at_task = ""
    end

    batch.vm.provider "virtualbox" do |vbox|
      vbox.memory = 1000
      vbox.cpus = 2
    end
  end

  config.vm.define "web1", primary: true do |web1|
    web1.vm.box = "bento/ubuntu-16.04"

    web1.vm.network :private_network, ip: "10.10.10.10"

    # Sync source code directories from host to guest
    case RUBY_PLATFORM
    when /mswin|msys|mingw|cygwin|bccwin|wince|emc/
        # Fix Windows file rights, otherwise Ansible tries to execute files
        web1.vm.synced_folder ".", "/vagrant", type:"virtualbox", :mount_options => ["dmode=755","fmode=644"]
    end

    web1.vm.provision "ansible_local" do |ansible|
      ansible.playbook = "ansible/vagrant-multi-server.yml"
      ansible.verbose = "v"
      ansible.inventory_path = "ansible/inventories/vagrant-multi/vagrant"
      ansible.skip_tags = "non-local"
      ansible.limit = 'web-servers'
      # ansible.extra_vars = { clear_module_cache: true }
      # ansible.tags = "modules,ckan,drupal"
      # ansible.start_at_task = ""
    end

    web1.vm.provider "virtualbox" do |vbox|
      vbox.memory = 3000
      vbox.cpus = 2
    end
  end



end
