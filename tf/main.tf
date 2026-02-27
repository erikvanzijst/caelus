terraform {
  required_version = ">= 1.0"
}

# Include all k8s resources
# Resources are defined in individual files under k8s/

# This file serves as the entry point
# All terraform files in this directory and subdirectories are automatically included
