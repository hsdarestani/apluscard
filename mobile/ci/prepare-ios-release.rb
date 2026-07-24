#!/usr/bin/env ruby
# frozen_string_literal: true

require 'fileutils'
require 'xcodeproj'

required = %w[
  IOS_BUNDLE_ID
  IOS_TEAM_ID
  IOS_VERSION_NAME
  IOS_BUILD_NUMBER
  IOS_PROVISIONING_PROFILE_NAME
]
required.each do |name|
  value = ENV[name]
  abort("Erforderliche Umgebungsvariable fehlt: #{name}") if value.nil? || value.strip.empty?
end

mobile_root = File.expand_path('..', __dir__)
ios_root = File.join(mobile_root, 'ios', 'App')
project_path = File.join(ios_root, 'App.xcodeproj')
app_dir = File.join(ios_root, 'App')
info_plist_path = File.join(app_dir, 'Info.plist')
entitlements_path = File.join(app_dir, 'App.entitlements')

abort("Xcode-Projekt fehlt: #{project_path}") unless File.directory?(project_path)
abort("Info.plist fehlt: #{info_plist_path}") unless File.file?(info_plist_path)

entitlements = {
  'aps-environment' => 'production',
  'com.apple.developer.associated-domains' => [
    'applinks:cards.smarbiz.sbs',
    'webcredentials:cards.smarbiz.sbs'
  ]
}
Xcodeproj::Plist.write_to_path(entitlements, entitlements_path)

info_plist = Xcodeproj::Plist.read_from_path(info_plist_path)
background_modes = Array(info_plist['UIBackgroundModes'])
background_modes << 'remote-notification' unless background_modes.include?('remote-notification')
info_plist['UIBackgroundModes'] = background_modes
Xcodeproj::Plist.write_to_path(info_plist, info_plist_path)

project = Xcodeproj::Project.open(project_path)
target = project.targets.find { |candidate| candidate.name == 'App' }
abort('Xcode Target "App" wurde nicht gefunden.') unless target

target.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['PRODUCT_BUNDLE_IDENTIFIER'] = ENV.fetch('IOS_BUNDLE_ID')
  settings['DEVELOPMENT_TEAM'] = ENV.fetch('IOS_TEAM_ID')
  settings['CODE_SIGN_STYLE'] = 'Manual'
  settings['CODE_SIGN_IDENTITY'] = 'Apple Distribution'
  settings['PROVISIONING_PROFILE_SPECIFIER'] = ENV.fetch('IOS_PROVISIONING_PROFILE_NAME')
  settings['CODE_SIGN_ENTITLEMENTS'] = 'App/App.entitlements'
  settings['MARKETING_VERSION'] = ENV.fetch('IOS_VERSION_NAME')
  settings['CURRENT_PROJECT_VERSION'] = ENV.fetch('IOS_BUILD_NUMBER')
  settings['TARGETED_DEVICE_FAMILY'] = '1,2'
end

project.save
puts "SAMS Card iOS vorbereitet: #{ENV.fetch('IOS_BUNDLE_ID')} · #{ENV.fetch('IOS_VERSION_NAME')} (#{ENV.fetch('IOS_BUILD_NUMBER')})"
