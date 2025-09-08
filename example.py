import time


def my_function():
    print("This is my_function")
    time.sleep(1)


def count_time_execution(func):
    print(f"STarting counting execution time of {func}")
    start_time = time.time()
    func()
    end_time = time.time()
    print(f"Total execution time: {end_time - start_time}")


if __name__ == '__main__':
    count_time_execution(my_function)