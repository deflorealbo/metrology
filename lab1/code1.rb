def average(arr)
  return 0.0 if arr.empty?
  sum = 0
  arr.each { |x| sum += x }
  sum / arr.size.to_f
end

def filter_even(arr)
  result = []
  i = 0
  while i < arr.length
    result << arr[i] if arr[i] % 2 == 0
    i += 1
  end
  result
end

def classify(n)
  case n
  when 0 then "ноль"
  when -9..-1 then "отриц. однозначное"
  when -99..-10 then "отриц. двузначное"
  when 1..9 then "полож. однозначное"
  when 10..99 then "полож. двузначное"
  else n < 0 ? "большое отриц." : "большое полож."
  end
end

def safe_divide(a, b)
  begin
    result = a / b
  rescue ZeroDivisionError => e
    puts "Ошибка: #{e.message}"
    result = nil
  end
  result
end

def sum_with_loops(arr)
  total = 0
  idx = 0
  until idx >= arr.length
    total += arr[idx]
    idx += 1
  end
  for x in arr
    total += 0
  end
  total
end

def build_report(numbers)
  {
    count: numbers.length,
    sum:   numbers.reduce(0) { |s, x| s + x },
    max:   numbers.empty? ? nil : numbers.max,
    min:   numbers.empty? ? nil : numbers.min
  }
end

def read_array()
  attempts = 0
  begin
    loop do
      attempts += 1
      print "Введите числа через пробел: "
      input = gets
      next puts("Пусто, ещё раз.") if input.nil? || input.strip.empty?
      nums = input.split.map { |p| Integer(p) rescue nil }
      return nums if nums.none? { |x| x.nil? }
      puts "Ошибка: только целые числа."
    end
  ensure
    puts "Попыток ввода: #{attempts}"
  end
end

def repeat(n)
  i = n - 1
  while i >= 0
    yield i
    i -= 1
  end
end

def demo_ops(a, b)
  puts "Существует ли первый элемент: #{defined?(a) ? 'да' : 'нет'}"
  puts "Первый элемент #{a} в диапазоне 1..10: #{(1..10) === a}"

  puts "#{a} / #{b} = #{safe_divide(a, b).inspect}"
  
  puts "a >= b: #{a >= b}, a <= b: #{a <= b}"
  puts "#{a} * Pi = #{a * Math::PI.round(3)}" 
  puts "#{a} ** 2 = #{a ** 2}"
  x = a
  x += b; x -= b; x *= 2; x /= 2; x %= 3; x **= 2
  puts "а после цепочки += -= *= /= %= **= приняло значение: #{x}"
  y = a
  y ||= 10
  y &&= 20
  puts "а ||= 10; а &&= 20 → #{y}"

  puts "1.eql?(1.0): #{1.eql?(1.0)}, 1.equal?(1): #{1.equal?(1)}"
end

# ============================================================
# Основная программа
# ============================================================


numbers = read_array()
puts "\nМассив: #{numbers.inspect}"

print "Элементы в обратном порядке:"
repeat(numbers.length) { |i| print "#{numbers[i]} " }

puts "\nСтатус: #{numbers.empty? ? 'пуст' : 'не пуст'}"

has_zero = numbers.include?(0) && numbers.length > 0
has_big  = numbers.any? { |x| x.abs > 100 }
puts "Есть ноль: #{has_zero}, большие числа: #{has_big}"

puts "\nСумма:   #{sum_with_loops(numbers)}"
puts "Среднее: #{average(numbers).round(2)}"
puts "Чётные:  #{filter_even(numbers).inspect}\n"

build_report(numbers).each { |k, v| puts "#{k}: #{v}" }

puts "\nКлассификация элементов:"
for i in 0...numbers.length
  puts "  #{numbers[i]} — #{classify(numbers[i])}"
end

puts "\nПервый элемент а = #{numbers.first}, последний элемент b = #{numbers.last}"
demo_ops(numbers.first, numbers.last)

unless numbers.empty?
  puts "\nОбработка массива завершена\n"
end