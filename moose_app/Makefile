###############################################################################
################### MOOSE Application Standard Makefile #######################
###############################################################################
#
# Optional Environment variables
# MOOSE_DIR        - Root directory of the MOOSE project
#
###############################################################################
# Use the MOOSE submodule if it exists and MOOSE_DIR is not set
MOOSE_SUBMODULE    := $(CURDIR)/moose
ifneq ($(wildcard $(MOOSE_SUBMODULE)/framework/Makefile),)
  MOOSE_DIR        ?= $(MOOSE_SUBMODULE)
else
  MOOSE_DIR        ?= $(shell dirname `pwd`)/moose
endif

# framework
FRAMEWORK_DIR      := $(MOOSE_DIR)/framework
include $(FRAMEWORK_DIR)/build.mk
include $(FRAMEWORK_DIR)/moose.mk

################################## MODULES ####################################
# To use certain physics included with MOOSE, set variables below to
# yes as needed.  Or set ALL_MODULES to yes to turn on everything (overrides
# other set variables).

ALL_MODULES                 := yes

CHEMICAL_REACTIONS          := no
CONTACT                     := no
ELECTROMAGNETICS            := no
EXTERNAL_PETSC_SOLVER       := no
FLUID_PROPERTIES            := no
FSI                         := no
FUNCTIONAL_EXPANSION_TOOLS  := no
GEOCHEMISTRY                := no
HEAT_TRANSFER               := no
LEVEL_SET                   := no
MISC                        := no
NAVIER_STOKES               := no
OPTIMIZATION                := no
PERIDYNAMICS                := no
PHASE_FIELD                 := no
POROUS_FLOW                 := no
RAY_TRACING                 := no
REACTOR                     := no
RDG                         := no
SHIFTED_BOUNDARY_METHOD     := no
SOLID_MECHANICS             := no
STOCHASTIC_TOOLS            := no
THERMAL_HYDRAULICS          := no
XFEM                        := no

include $(MOOSE_DIR)/modules/modules.mk
###############################################################################

# Optional base application whose objects are registered alongside the framework, modules and
# VIBORA's own objects, for example your group's MOOSE application. VIBORA sets these from
# base_app in config.local.json; leave them empty to use the framework and modules only.
#   VIBORA_BASE_APP      class name, e.g. MyApp (header MyApp.h)
#   VIBORA_BASE_APP_DIR  source tree containing include/base and lib/
#   VIBORA_BASE_APP_LIB  library stem, e.g. my for lib/libmy-$(METHOD).la
ifneq ($(VIBORA_BASE_APP),)
  ADDITIONAL_INCLUDES += -I$(VIBORA_BASE_APP_DIR)/include/base
  ADDITIONAL_LIBS     += $(VIBORA_BASE_APP_DIR)/lib/lib$(VIBORA_BASE_APP_LIB)-$(METHOD).la
  ADDITIONAL_CPPFLAGS += -DVIBORA_BASE_APP=$(VIBORA_BASE_APP) -DVIBORA_BASE_APP_HEADER="\"$(VIBORA_BASE_APP).h\""
endif

# dep apps
APPLICATION_DIR    := $(CURDIR)
APPLICATION_NAME   := vibora_physics
BUILD_EXEC         := yes
GEN_REVISION       := no
include            $(FRAMEWORK_DIR)/app.mk

###############################################################################
# Additional special case targets should be added here
