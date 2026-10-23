#include "ViboraPhysicsApp.h"
#include "Moose.h"
#include "AppFactory.h"
#include "ModulesApp.h"
#ifdef VIBORA_BASE_APP
#include VIBORA_BASE_APP_HEADER
#endif
#include "MooseSyntax.h"

InputParameters
ViboraPhysicsApp::validParams()
{
  InputParameters params = MooseApp::validParams();
  params.set<bool>("use_legacy_material_output") = false;
  params.set<bool>("use_legacy_initial_residual_evaluation_behavior") = false;
  return params;
}

ViboraPhysicsApp::ViboraPhysicsApp(const InputParameters & parameters) : MooseApp(parameters)
{
  ViboraPhysicsApp::registerAll(_factory, _action_factory, _syntax);
}

ViboraPhysicsApp::~ViboraPhysicsApp() {}

void
ViboraPhysicsApp::registerAll(Factory & f, ActionFactory & af, Syntax & syntax)
{
#ifdef VIBORA_BASE_APP
  // A configured base application registers its own objects together with the framework and modules.
  VIBORA_BASE_APP::registerAll(f, af, syntax);
#else
  ModulesApp::registerAllObjects<ViboraPhysicsApp>(f, af, syntax);
#endif
  Registry::registerObjectsTo(f, {"ViboraPhysicsApp"});
  Registry::registerActionsTo(af, {"ViboraPhysicsApp"});

  /* register custom execute flags, action syntax, etc. here */
}

void
ViboraPhysicsApp::registerApps()
{
  registerApp(ViboraPhysicsApp);
}

/***************************************************************************************************
 *********************** Dynamic Library Entry Points - DO NOT MODIFY ******************************
 **************************************************************************************************/
extern "C" void
ViboraPhysicsApp__registerAll(Factory & f, ActionFactory & af, Syntax & s)
{
  ViboraPhysicsApp::registerAll(f, af, s);
}
extern "C" void
ViboraPhysicsApp__registerApps()
{
  ViboraPhysicsApp::registerApps();
}
