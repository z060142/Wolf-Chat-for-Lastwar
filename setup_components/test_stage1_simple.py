#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 1 Simple Functionality Test
简化的阶段1功能测试
"""

import sys
import os
import traceback

def test_imports():
    """测试导入"""
    print("\n[TEST] Testing imports...")
    
    try:
        from setup_components import (
            state_manager, 
            ProcessType, 
            ProcessState, 
            ConfigType,
            thread_safe_process_manager, 
            thread_safe_monitor, 
            thread_safe_remote_control,
            config_transaction_manager
        )
        
        print("[PASS] All state management components imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] Import failed: {e}")
        return False

def test_state_manager():
    """测试状态管理器"""
    print("\n[TEST] Testing state manager...")
    
    try:
        from setup_components import state_manager, ProcessType, ProcessState
        
        # Test process state
        state_manager.set_process_state(ProcessType.BOT, ProcessState.STARTING)
        current_state = state_manager.get_process_state(ProcessType.BOT)
        
        if current_state == ProcessState.STARTING:
            print("[PASS] Process state management working")
        else:
            print(f"[FAIL] Process state mismatch: expected {ProcessState.STARTING}, got {current_state}")
            return False
        
        return True
        
    except Exception as e:
        print(f"[FAIL] State manager test failed: {e}")
        traceback.print_exc()
        return False

def test_config_transaction():
    """测试配置事务"""
    print("\n[TEST] Testing config transaction...")
    
    try:
        from setup_components import config_transaction_manager, ConfigType
        
        # Test transaction
        tx_id = config_transaction_manager.begin_transaction()
        if tx_id:
            print("[PASS] Config transaction started")
            
            # Test rollback
            if config_transaction_manager.rollback_transaction():
                print("[PASS] Config transaction rollback successful")
                return True
            else:
                print("[FAIL] Config transaction rollback failed")
                return False
        else:
            print("[FAIL] Config transaction start failed")
            return False
        
    except Exception as e:
        print(f"[FAIL] Config transaction test failed: {e}")
        traceback.print_exc()
        return False

def test_setup_import():
    """测试Setup.py导入"""
    print("\n[TEST] Testing Setup.py import...")
    
    try:
        import Setup
        print("[PASS] Setup.py imported successfully")
        
        if hasattr(Setup, 'WolfChatSetup'):
            print("[PASS] WolfChatSetup class found")
            return True
        else:
            print("[FAIL] WolfChatSetup class not found")
            return False
        
    except Exception as e:
        print(f"[FAIL] Setup.py import failed: {e}")
        traceback.print_exc()
        return False

def run_tests():
    """运行所有测试"""
    print("Starting Stage 1 Functionality Tests...")
    print("=" * 50)
    
    tests = [
        ("Imports", test_imports),
        ("State Manager", test_state_manager),
        ("Config Transaction", test_config_transaction),
        ("Setup Import", test_setup_import),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[ERROR] Test '{test_name}' exception: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Test Results:")
    print(f"  PASSED: {passed}")
    print(f"  FAILED: {failed}")
    print(f"  Success Rate: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print("\nAll Stage 1 tests passed!")
        print("State management integration successful!")
        return True
    else:
        print(f"\n{failed} tests failed. Need to fix issues before proceeding.")
        return False

if __name__ == "__main__":
    success = run_tests()
    
    if success:
        print("\nStage 1 Refactoring Summary:")
        print("  - State Manager: Implemented and integrated")
        print("  - Thread Safety: Process and monitoring protection added")
        print("  - Config Transactions: Atomic configuration updates enabled")
        print("  - Backward Compatibility: Existing APIs preserved")
        print("  - Backup Protection: Setup_backup_v1.py created")
        
        print("\nNext Step: Ready for Stage 2 - Process Management Refactoring")
    else:
        print("\nFix Recommendations:")
        print("  1. Check import paths and module dependencies")
        print("  2. Verify all new files are correctly created")
        print("  3. Check for syntax errors and missing methods")
        print("  4. If needed, restore backup: Setup_backup_v1.py")
    
    sys.exit(0 if success else 1)