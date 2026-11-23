Feature: Unified CLI mini-framework for Python scripts

  Background:
    Given the CLI framework is available
    And the following CLI arguments are supported:
      | argument         | short | description                             |
      | input            |       | File or directory to process            |
      | --output         |       | Output file or directory                |
      | --recursive      |       | Enable recursive directory traversal    |
      | --include        |       | Include filter (glob pattern)           |
      | --exclude        |       | Exclude filter (glob pattern)           |
      | --dry-run        |       | Simulate actions without modifying      |
      | --verbose        | -v    | Increase verbosity (stackable)          |
      | --completion       |       | Print bash completion script and exit   |
      | --self-install   |       | Install script and create symlink       |
      | --self-uninstall |       | Uninstall script and remove symlink     |

  Scenario: Process a single file
    Given the user provides "sample.txt"
    When the processor runs
    Then the file "sample.txt" should be processed exactly once

  Scenario: Process files in a directory non-recursively
    Given the user provides "mydir"
    And "mydir" contains files directly
    When the processor runs
    Then only files directly in "mydir" should be processed
    And files in subdirectories should not be processed

  Scenario: Process files recursively in a directory
    Given the user provides "mydir --recursive"
    And "mydir" contains files in nested subdirectories
    When the processor runs
    Then all files in "mydir" and its subdirectories should be processed

  Scenario: Process files with include filter
    Given the user provides "mydir --include *.txt"
    And "mydir" contains ".txt" and ".md" files
    When the processor runs
    Then only ".txt" files should be processed
    And ".md" files should be excluded

  Scenario: Process files with exclude filter
    Given the user provides "mydir --exclude *.log"
    And "mydir" contains ".log" and ".txt" files
    When the processor runs
    Then ".log" files should be excluded
    And other files should be processed

  Scenario: Combine include and exclude filters
    Given the user provides "mydir --include *.txt --exclude *-draft.txt"
    And "mydir" contains "report.txt" and "report-draft.txt"
    When the processor runs
    Then "report.txt" should be processed
    And "report-draft.txt" should be excluded

  Scenario: Dry-run mode does not modify files
    Given the user provides "mydir --dry-run"
    And the processor would normally modify files
    When the processor runs
    Then no files should be modified
    And the operations should be simulated only

  Scenario: Verbose mode outputs processing information
    Given the user provides "mydir --verbose"
    When the processor runs
    Then informational messages should be printed for each processed file

  Scenario: Multiple verbose flags increase verbosity
    Given the user provides "mydir -vvv"
    When the processor runs
    Then debug messages should be displayed including directory entry

  Scenario: Specify output file or directory
    Given the user provides "sample.txt --output result.json"
    When the processor runs
    Then the output should be written to "result.json"

  Scenario: Install the script
    When the script is run with the --self-install flag
    Then it should install the script to ~/.local/share/TangoMan75/<script_name>
    And generate completion script if not exists
    And create a symlink in ~/.local/bin
    And copy completion script to install directory
    And add completion source to .bashrc
    And output installation messages

  Scenario: Uninstall the script
    When the script is run with the --self-uninstall flag
    Then it should remove the symlink from ~/.local/bin
    And remove the script from ~/.local/share/TangoMan75/<script_name>
    And remove completion source from .bashrc
    And output uninstallation messages

  Scenario: Reject a missing input path
    Given the user provides an input path that does not exist
    When the processor runs
    Then an input path error should be reported

  Scenario: Dry-run file listing does not write output
    Given the file lister is given an output path
    When it processes a file with --dry-run
    Then the output path should not be created

  Scenario: Print own completion script with --completion
    Given a Python script path
    When the script is run with the --completion flag
    Then it should print a bash completion script to stdout
    And the completion script should list the script's own options

  Scenario: Dispatch installation with installer.py
    Given a Python script path
    When installer.py is run with the install command and that path
    Then it should copy the script to its private installation directory
    And it should create a symlink in ~/.local/bin
    And it should run the target script with --completion to create a shell completion script

  Scenario: Skip completion when target lacks --completion
    Given a Python script that does not support --completion
    When installer.py is run with the install command and that path
    Then it should copy the script to its private installation directory
    And it should warn that completion is skipped
    And it should not create a shell completion script

  Scenario: Dispatch uninstallation with installer.py
    Given a Python script path
    When installer.py is run with the uninstall command and that path
    Then it should remove the private installation directory
    And it should remove the symlink from ~/.local/bin
    And it should remove shell completion configuration

  Scenario: Display alert boxes
    Given the CLI framework has alert functions
    When alert_success is called with "Operation completed"
    Then it should display a green alert box
    And alert_danger should display a red alert box
    And alert_warning should display an orange alert box
    And alert_info should display a blue alert box
