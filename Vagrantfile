# -*- mode: ruby -*-
# vi: set ft=ruby :
#
# This Vagrantfile sets up a virtual machine and installs the YTP service
# on it to create a local development environment.
#
# Tested with Vagrant 1.6.1 and VirtualBox 4.3.10 on Ubuntu 14.04 64-bit

VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  config.vm.define "ytpdb" do |ytpdb|
    ytpdb.vm.box = "bento/ubuntu-16.04"

    ytpdb.vm.network :private_network, ip: "10.10.10.20"

    # Sync source code directories from host to guest
    case RUBY_PLATFORM
    when /mswin|msys|mingw|cygwin|bccwin|wince|emc/
        # Fix Windows file rights, otherwise Ansible tries to execute files
        ytpdb.vm.synced_folder ".", "/vagrant", type:"virtualbox", :mount_options => ["dmode=755","fmode=644"]
    end

    ytpdb.vm.provision "ansible_local" do |ansible|
      ansible.playbook = "ansible/cluster-dbserver.yml"
      ansible.verbose = "v"
      ansible.inventory_path = "ansible/inventories/vagrant"
      ansible.skip_tags = "non-local,postfix"
      ansible.limit = 'all'
      # ansible.extra_vars = { clear_module_cache: true }
      # ansible.tags = "modules,ckan,drupal"
      # ansible.start_at_task = ""
    end

    ytpdb.vm.provider "virtualbox" do |vbox|
      vbox.memory = 3000
      vbox.cpus = 2
    end
  end

  config.vm.define "ytpweb1" do |ytpweb1|
    ytpweb1.vm.box = "bento/ubuntu-16.04"

    ytpweb1.vm.network :private_network, ip: "10.10.10.10"

    # Sync source code directories from host to guest
    case RUBY_PLATFORM
    when /mswin|msys|mingw|cygwin|bccwin|wince|emc/
        # Fix Windows file rights, otherwise Ansible tries to execute files
        ytpweb1.vm.synced_folder ".", "/vagrant", type:"virtualbox", :mount_options => ["dmode=755","fmode=644"]
    end

    ytpweb1.vm.provision "ansible_local" do |ansible|
      ansible.playbook = "ansible/cluster-webserver.yml"
      ansible.verbose = "v"
      ansible.inventory_path = "ansible/inventories/vagrant"
      ansible.skip_tags = "non-local,postfix"
      ansible.limit = 'all'
      # ansible.extra_vars = { clear_module_cache: true }
      # ansible.tags = "modules,ckan,drupal"
      # ansible.start_at_task = ""
    end

    ytpweb1.vm.provider "virtualbox" do |vbox|
      vbox.memory = 3000
      vbox.cpus = 2
    end
  end

  config.vm.define "ytpweb2" do |ytpweb2|
    ytpweb2.vm.box = "bento/ubuntu-16.04"

    ytpweb2.vm.network :private_network, ip: "10.10.10.11"

    # Sync source code directories from host to guest
    case RUBY_PLATFORM
    when /mswin|msys|mingw|cygwin|bccwin|wince|emc/
        # Fix Windows file rights, otherwise Ansible tries to execute files
        ytpweb2.vm.synced_folder ".", "/vagrant", type:"virtualbox", :mount_options => ["dmode=755","fmode=644"]
    end

    ytpweb2.vm.provision "ansible_local" do |ansible|
      ansible.playbook = "ansible/cluster-webserver.yml"
      ansible.verbose = "v"
      ansible.inventory_path = "ansible/inventories/vagrant"
      ansible.skip_tags = "non-local,postfix"
      ansible.limit = 'all'
      # ansible.extra_vars = { clear_module_cache: true }
      # ansible.tags = "modules,ckan,drupal"
      # ansible.start_at_task = ""
    end

    ytpweb2.vm.provider "virtualbox" do |vbox|
      vbox.memory = 3000
      vbox.cpus = 2
    end
  end


  # http://docs.vagrantup.com/v2/multi-machine/index.html
  #config.vm.define "db" do |db|
end
